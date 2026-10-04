# wiki-speedrun

Find the shortest click-path between two Wikipedia articles — with BFS, concurrent BFS, and semantic (AI-guided) BFS solvers, plus a web UI.

## Solvers (`wiki_speedrun/` — originals)

| File | Algorithm |
|---|---|
| `bfs.py` | Classic breadth-first search (guaranteed shortest path) |
| `concurrent_bfs.py` | Level-parallel BFS with `ThreadPoolExecutor` |
| `semantic_bfs.py` + `semantic.py` | BFS with `SentenceTransformer` re-ranking toward the target |
| `wikipedia.py` | Article fetching + link extraction (cached) |

## Web UI

FastAPI backend + vanilla JS frontend with live progress, path timeline, stats, and an interactive explored-graph view.

The UI never edits `wiki_speedrun/` — it uses **copies** in `backend/` (`wikipedia.py`, `semantic.py`, `engine.py` streaming search with progress callbacks, `max_pages` / `max_depth` limits, cancel).

Enter a **Source** and **Target** as full Wikipedia URLs (`https://en.wikipedia.org/wiki/Potato`) or plain titles (`Potato`).

### Run

Requires **Python 3.11**.

```bash
# --- option A: python venv (Python 3.11) ---
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# --- option B: conda (Python 3.11) ---
conda create -n wiki-speedrun python=3.11 -y
conda activate wiki-speedrun

pip install -r requirements.txt
uvicorn app:app --reload
# open http://127.0.0.1:8000
```

For semantic search (optional, ~400MB model download on first use):

```bash
pip install sentence-transformers torch
```

### API

- `POST /api/search` — `{start, target, algorithm, max_pages, max_depth}` → `{job_id}`. `start`/`target` accept titles (`"Potato"`) or URLs.
- `GET /api/jobs/{job_id}?graph=true` — poll for status, live logs, `path`, `stats`, `graph {nodes, edges, path}`.
- `DELETE /api/jobs/{job_id}` — cancel a running search.
- `GET /api/health` — backend status.

### CLI (original)

```bash
python main.py
```

Edit `START_URL` / `TARGET_URL` in `main.py` to try other pairs.
