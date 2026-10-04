"""Streaming search engine for the web UI.

Mirrors the algorithms in `wiki_speedrun/bfs.py`, `concurrent_bfs.py` and
`semantic_bfs.py` (those originals are left untouched) with progress
callbacks, page/depth limits, cancellation, and graph capture so the
frontend can render live progress and the explored graph.
"""
from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


class SearchCancelled(Exception):
    pass


class SearchLimitReached(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class SearchStats:
    pages_visited: int = 0
    max_queue: int = 0
    elapsed: float = 0.0
    reason: str = ""


# Callback fired on every visited page:
#   on_visit(current_url, pages_visited, queue_size)
ProgressCallback = Callable[[str, int, int], None]


def reconstruct_path(parent: Dict[str, Optional[str]], target_url: str) -> List[str]:
    path: List[str] = []
    current: Optional[str] = target_url
    while current is not None:
        path.append(current)
        current = parent.get(current)
    path.reverse()
    return path


def _check_limits(pages_visited: int, max_pages: int):
    if pages_visited >= max_pages:
        raise SearchLimitReached(f"Stopped after visiting {pages_visited} pages (max_pages={max_pages}).")


def title_of(url: str) -> str:
    from urllib.parse import unquote

    t = url.split("/wiki/", 1)[-1]
    return unquote(t).replace("_", " ")


def bfs_search(
    wiki_client,
    start_url: str,
    target_url: str,
    max_pages: int = 2000,
    max_depth: int = 6,
    on_visit: Optional[ProgressCallback] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    parent: Optional[Dict[str, Optional[str]]] = None,
    visit_order: Optional[List[str]] = None,
) -> tuple[Optional[List[str]], SearchStats]:
    stats = SearchStats()
    t0 = time.time()
    queue: deque[str] = deque([start_url])
    depth: Dict[str, int] = {start_url: 0}
    if parent is None:
        parent = {start_url: None}
    else:
        parent[start_url] = None
    visited = {start_url}

    stats.max_queue = 1

    while queue:
        if should_stop and should_stop():
            raise SearchCancelled()
        current_url = queue.popleft()
        stats.pages_visited += 1
        stats.max_queue = max(stats.max_queue, len(queue))
        if visit_order is not None:
            visit_order.append(current_url)
        if on_visit:
            on_visit(current_url, stats.pages_visited, len(queue))

        if current_url == target_url:
            stats.elapsed = time.time() - t0
            return reconstruct_path(parent, target_url), stats

        _check_limits(stats.pages_visited, max_pages)

        if depth[current_url] >= max_depth:
            continue

        links = wiki_client.get_all_valid_links(base_url=current_url)
        for link in links:
            if should_stop and should_stop():
                raise SearchCancelled()
            if link in visited:
                continue
            visited.add(link)
            parent[link] = current_url
            depth[link] = depth[current_url] + 1
            if link == target_url:
                stats.pages_visited += 1
                if visit_order is not None:
                    visit_order.append(link)
                if on_visit:
                    on_visit(link, stats.pages_visited, len(queue))
                stats.elapsed = time.time() - t0
                return reconstruct_path(parent, target_url), stats
            queue.append(link)
        stats.max_queue = max(stats.max_queue, len(queue))

    stats.elapsed = time.time() - t0
    return None, stats


def concurrent_bfs_search(
    wiki_client,
    start_url: str,
    target_url: str,
    max_pages: int = 2000,
    max_depth: int = 6,
    max_workers: int = 8,
    on_visit: Optional[ProgressCallback] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    parent: Optional[Dict[str, Optional[str]]] = None,
    visit_order: Optional[List[str]] = None,
) -> tuple[Optional[List[str]], SearchStats]:
    stats = SearchStats()
    t0 = time.time()
    queue: deque[str] = deque([start_url])
    depth: Dict[str, int] = {start_url: 0}
    if parent is None:
        parent = {start_url: None}
    else:
        parent[start_url] = None
    visited = {start_url}

    def fetch_many(urls: List[str]) -> Dict[str, list]:
        results: Dict[str, list] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(wiki_client.get_all_valid_links, u): u for u in urls}
            for fut in as_completed(futures):
                u = futures[fut]
                try:
                    results[u] = fut.result()
                except Exception:
                    results[u] = []
        return results

    while queue:
        if should_stop and should_stop():
            raise SearchCancelled()
        # Process the queue in small batches so progress stays live and
        # max_pages / cancel take effect promptly. Fetching a whole BFS
        # level (often 1000+ URLs) up-front would stall with no updates.
        batch_size = max_workers * 2
        batch_urls = [queue.popleft() for _ in range(min(len(queue), batch_size))]
        stats.max_queue = max(stats.max_queue, len(queue) + len(batch_urls))
        results = fetch_many(batch_urls)

        for current_url in batch_urls:
            if should_stop and should_stop():
                raise SearchCancelled()
            stats.pages_visited += 1
            if visit_order is not None:
                visit_order.append(current_url)
            if on_visit:
                on_visit(current_url, stats.pages_visited, len(queue))

            if current_url == target_url:
                stats.elapsed = time.time() - t0
                return reconstruct_path(parent, target_url), stats

            _check_limits(stats.pages_visited, max_pages)

            if depth[current_url] >= max_depth:
                continue

            for link in results.get(current_url, []):
                if link in visited:
                    continue
                visited.add(link)
                parent[link] = current_url
                depth[link] = depth[current_url] + 1
                if link == target_url:
                    stats.pages_visited += 1
                    if visit_order is not None:
                        visit_order.append(link)
                    if on_visit:
                        on_visit(link, stats.pages_visited, len(queue))
                    stats.elapsed = time.time() - t0
                    return reconstruct_path(parent, target_url), stats
                queue.append(link)
        stats.max_queue = max(stats.max_queue, len(queue))

    stats.elapsed = time.time() - t0
    return None, stats


def semantic_bfs_search(
    wiki_client,
    ranker,
    start_url: str,
    target_url: str,
    max_pages: int = 2000,
    max_depth: int = 6,
    on_visit: Optional[ProgressCallback] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    parent: Optional[Dict[str, Optional[str]]] = None,
    visit_order: Optional[List[str]] = None,
) -> tuple[Optional[List[str]], SearchStats]:
    stats = SearchStats()
    t0 = time.time()
    queue: deque[str] = deque([start_url])
    depth: Dict[str, int] = {start_url: 0}
    if parent is None:
        parent = {start_url: None}
    else:
        parent[start_url] = None
    visited = {start_url}

    while queue:
        if should_stop and should_stop():
            raise SearchCancelled()
        current_url = queue.popleft()
        stats.pages_visited += 1
        stats.max_queue = max(stats.max_queue, len(queue))
        if visit_order is not None:
            visit_order.append(current_url)
        if on_visit:
            on_visit(current_url, stats.pages_visited, len(queue))

        if current_url == target_url:
            stats.elapsed = time.time() - t0
            return reconstruct_path(parent, target_url), stats

        _check_limits(stats.pages_visited, max_pages)

        if depth[current_url] >= max_depth:
            continue

        links = wiki_client.get_all_valid_links(base_url=current_url)
        candidates = [l for l in links if l not in visited]
        try:
            ranked = ranker.rank(candidates_list=candidates, target_url=target_url)
            ordered = [u for u, _ in ranked]
        except Exception:
            ordered = candidates

        for link in ordered:
            if should_stop and should_stop():
                raise SearchCancelled()
            if link in visited:
                continue
            visited.add(link)
            parent[link] = current_url
            depth[link] = depth[current_url] + 1
            if link == target_url:
                stats.pages_visited += 1
                if visit_order is not None:
                    visit_order.append(link)
                if on_visit:
                    on_visit(link, stats.pages_visited, len(queue))
                stats.elapsed = time.time() - t0
                return reconstruct_path(parent, target_url), stats
            queue.append(link)
        stats.max_queue = max(stats.max_queue, len(queue))

    stats.elapsed = time.time() - t0
    return None, stats


ALGORITHMS = ("bfs", "concurrent", "semantic")
