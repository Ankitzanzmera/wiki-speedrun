"""Wikipedia Speedrun web UI — FastAPI server.

Run with:
    uvicorn app:app --reload
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, unquote, urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel, Field

from backend.engine import (
    SearchCancelled,
    SearchLimitReached,
    bfs_search,
    concurrent_bfs_search,
    semantic_bfs_search,
    title_of,
)
from backend.wikipedia import WikipediaClient

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Wikipedia Speedrun")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Shared clients (WikipediaClient has an internal cache + session).
_wiki_client = WikipediaClient()
_ranker = None
_ranker_lock = threading.Lock()
_ranker_error: Optional[str] = None


def get_ranker():
    """Lazily load the semantic model on first use (it's a big download)."""
    global _ranker, _ranker_error
    with _ranker_lock:
        if _ranker is not None:
            return _ranker
        if _ranker_error is not None:
            raise RuntimeError(_ranker_error)
        try:
            from backend.semantic import SemanticRanker

            _ranker = SemanticRanker()
            return _ranker
        except Exception as e:  # missing deps, no torch, download failure...
            _ranker_error = (
                f"Semantic model unavailable: {e}. "
                "Install with `pip install sentence-transformers torch` and retry."
            )
            raise RuntimeError(_ranker_error)


def to_wiki_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty article reference.")
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        if "wikipedia.org" not in parsed.netloc:
            raise ValueError("URL must be an English Wikipedia article.")
        path = parsed.path
        if not path.startswith("/wiki/"):
            raise ValueError("URL must look like https://en.wikipedia.org/wiki/Article")
        title = path.split("/wiki/", 1)[-1].split("#")[0]
        title = unquote(title).strip().replace(" ", "_")
        if not title:
            raise ValueError("Could not parse article title from URL.")
        return f"https://en.wikipedia.org/wiki/{quote(title, safe='()/_,:$@!*')}"
    # Plain title, e.g. "Barack Obama"
    title = raw.replace(" ", "_").strip()
    # Allow pasted "Potato" or "Potato (disambiguation)" etc.
    if title.startswith("/wiki/"):
        title = title[len("/wiki/"):]
    title = unquote(title)
    return f"https://en.wikipedia.org/wiki/{quote(title, safe='()/_,:$@!*')}"


# ---------------------------------------------------------------- jobs
@dataclass
class Job:
    id: str
    algorithm: str
    start_url: str
    target_url: str
    max_pages: int
    max_depth: int
    status: str = "queued"  # queued | running | done | error | cancelled
    current_url: str = ""
    pages_visited: int = 0
    queue_size: int = 0
    elapsed: float = 0.0
    logs: List[str] = field(default_factory=list)
    visit_order: List[str] = field(default_factory=list)
    parent: Dict[str, Optional[str]] = field(default_factory=dict)
    path: Optional[List[str]] = None
    error: Optional[str] = None
    stats: Dict = field(default_factory=dict)
    cancel_requested: bool = False
    started_at: float = 0.0
    finished_at: float = 0.0

    def log(self, msg: str):
        self.logs.append(msg)
        if len(self.logs) > 300:
            self.logs = self.logs[-300:]


jobs: Dict[str, Job] = {}
jobs_lock = threading.Lock()

GRAPH_NODE_CAP = 600  # cap graph payload sent to frontend


def _run_job(job: Job):
    job.status = "running"
    job.started_at = time.time()
    job.log(f"Starting {job.algorithm} search…")
    job.log(f"From: {title_of(job.start_url)}")
    job.log(f"To: {title_of(job.target_url)}")
    t0 = time.time()

    def on_visit(url: str, visited: int, qsize: int):
        job.current_url = url
        job.pages_visited = visited
        job.queue_size = qsize
        job.elapsed = time.time() - t0
        if visited <= 12 or visited % 5 == 0:
            job.log(f"[{visited}] Visiting {title_of(url)}")

    def should_stop() -> bool:
        return job.cancel_requested

    try:
        if job.algorithm == "semantic":
            job.log("Loading semantic model (first run downloads ~400MB)…")
            ranker = get_ranker()
            job.log("Semantic model ready. Ranking links by similarity…")
            path, stats = semantic_bfs_search(
                _wiki_client, ranker,
                job.start_url, job.target_url,
                max_pages=job.max_pages, max_depth=job.max_depth,
                on_visit=on_visit, should_stop=should_stop,
                parent=job.parent, visit_order=job.visit_order,
            )
        elif job.algorithm == "concurrent":
            path, stats = concurrent_bfs_search(
                _wiki_client,
                job.start_url, job.target_url,
                max_pages=job.max_pages, max_depth=job.max_depth,
                on_visit=on_visit, should_stop=should_stop,
                parent=job.parent, visit_order=job.visit_order,
            )
        else:
            path, stats = bfs_search(
                _wiki_client,
                job.start_url, job.target_url,
                max_pages=job.max_pages, max_depth=job.max_depth,
                on_visit=on_visit, should_stop=should_stop,
                parent=job.parent, visit_order=job.visit_order,
            )

        job.elapsed = time.time() - t0
        job.finished_at = job.elapsed
        if path:
            job.status = "done"
            job.path = path
            job.log(f"Found path in {len(path)-1} clicks, {stats.pages_visited} pages, {job.elapsed:.1f}s")
            job.stats = {
                "time_taken": round(job.elapsed, 2),
                "pages_visited": stats.pages_visited,
                "path_length": len(path),
                "clicks": len(path) - 1,
                "max_queue": stats.max_queue,
            }
        else:
            job.status = "error"
            job.error = (
                f"No path found within max_pages={job.max_pages}, max_depth={job.max_depth}. "
                "Try raising the limits or a different algorithm."
            )
            job.log(job.error)
            job.stats = {
                "time_taken": round(job.elapsed, 2),
                "pages_visited": stats.pages_visited,
                "path_length": 0,
                "clicks": 0,
                "max_queue": stats.max_queue,
            }
    except SearchCancelled:
        job.status = "cancelled"
        job.elapsed = time.time() - t0
        job.log("Search cancelled.")
    except SearchLimitReached as e:
        job.status = "error"
        job.elapsed = time.time() - t0
        job.error = str(e) + " No path found yet — raise max_pages/max_depth and retry."
        job.log(job.error)
        job.stats = {
            "time_taken": round(job.elapsed, 2),
            "pages_visited": job.pages_visited,
            "path_length": 0,
            "clicks": 0,
            "max_queue": job.queue_size,
        }
    except RuntimeError as e:
        job.status = "error"
        job.error = str(e)
        job.log(job.error)
    except Exception as e:  # noqa: BLE001
        job.status = "error"
        job.error = f"Search failed: {e}"
        job.log(job.error)


def job_to_dict(job: Job, include_graph: bool = True) -> dict:
    data = {
        "id": job.id,
        "algorithm": job.algorithm,
        "start_url": job.start_url,
        "target_url": job.target_url,
        "status": job.status,
        "current_url": job.current_url,
        "current_title": title_of(job.current_url) if job.current_url else "",
        "pages_visited": job.pages_visited,
        "queue_size": job.queue_size,
        "elapsed": round(job.elapsed, 1),
        "logs": job.logs[-120:],
        "path": job.path,
        "path_titles": [title_of(u) for u in job.path] if job.path else None,
        "error": job.error,
        "stats": job.stats,
    }
    if include_graph:
        visit = job.visit_order[:GRAPH_NODE_CAP]
        visit_set = set(visit)
        path_set = set(job.path or [])
        nodes = [{"id": u, "label": title_of(u)} for u in visit]
        if job.path:
            for u in job.path:
                if u not in visit_set:
                    nodes.append({"id": u, "label": title_of(u)})
                    visit_set.add(u)
        node_ids = visit_set
        edges = []
        for child, par in job.parent.items():
            if par is None:
                continue
            if child not in node_ids or par not in node_ids:
                continue
            edges.append({"from": par, "to": child})
            if len(edges) >= GRAPH_NODE_CAP * 2:
                break
        data["graph"] = {
            "nodes": nodes,
            "edges": edges,
            "path": job.path or [],
            "start": job.start_url,
            "target": job.target_url,
        }
    return data


# ---------------------------------------------------------------- API
class SearchRequest(BaseModel):
    start: str = Field(description="Start article title or URL")
    target: str = Field(description="Target article title or URL")
    algorithm: str = Field(default="bfs", description="bfs | concurrent | semantic")
    max_pages: int = Field(default=800, ge=10, le=20000)
    max_depth: int = Field(default=5, ge=1, le=10)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/search")
def start_search(req: SearchRequest):
    algo = req.algorithm.lower()
    if algo not in ("bfs", "concurrent", "semantic"):
        raise HTTPException(400, "algorithm must be bfs | concurrent | semantic")
    try:
        start_url = to_wiki_url(req.start)
        target_url = to_wiki_url(req.target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if start_url == target_url:
        raise HTTPException(400, "Start and target are the same article.")

    job = Job(
        id=uuid.uuid4().hex[:12],
        algorithm=algo,
        start_url=start_url,
        target_url=target_url,
        max_pages=req.max_pages,
        max_depth=req.max_depth,
    )
    with jobs_lock:
        jobs[job.id] = job
    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()
    return {"job_id": job.id, **job_to_dict(job, include_graph=False)}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, graph: bool = True):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id")
    return job_to_dict(job, include_graph=graph)


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job id")
    job.cancel_requested = True
    return {"status": "cancelling", "id": job_id}


@app.get("/api/health")
def health():
    return {"status": "ok", "jobs": len(jobs)}
