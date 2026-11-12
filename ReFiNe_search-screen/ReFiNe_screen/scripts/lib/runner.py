"""Generic resumable, parallel per-paper loop shared by the screening stages.

Replaces the copy-pasted ThreadPoolExecutor loops in screen_abstract.py and
screen_fulltext.py. Each stage supplies:
  - items:     list of records, each with a unique id under `id_key`
  - is_done:   fn(item) -> str | None   — a skip reason if already finished
  - work:      fn(item) -> dict         — produces the artifact (must include "status")
  - describe:  fn(artifact) -> str      — short per-paper log suffix (optional)
and the runner writes <artifact_dir>/<id>.json, prints progress, and honours
the circuit breaker (no new papers start once it has tripped).
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from llm_client import CircuitBreaker


@dataclass
class RunStats:
    done: int = 0
    skipped: int = 0
    failed: int = 0
    not_started: int = 0
    statuses: dict = field(default_factory=dict)
    aborted: bool = False


def read_status(path: Path) -> str | None:
    """Status of an existing artifact, or None if missing/corrupt."""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("status")
    except (OSError, json.JSONDecodeError):
        return None


def run_items(items: list[dict], *, id_key: str, artifact_dir: Path,
              is_done: Callable[[dict], str | None],
              work: Callable[[dict], dict],
              describe: Callable[[dict], str] = lambda a: "",
              workers: int = 2,
              breaker: CircuitBreaker | None = None) -> RunStats:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stats = RunStats()
    lock = threading.Lock()
    n = len(items)

    def bump(attr: str) -> None:
        with lock:
            setattr(stats, attr, getattr(stats, attr) + 1)

    def process(idx: int, item: dict) -> None:
        pid = item[id_key]
        if breaker is not None and breaker.tripped.is_set():
            bump("not_started")
            return
        reason = is_done(item)
        if reason:
            print(f"[{idx}/{n}] {pid}: skipped ({reason})", flush=True)
            bump("skipped")
            return
        t0 = time.time()
        try:
            artifact = work(item)
        except Exception as exc:  # noqa: BLE001 — conversion failure etc.; keep going
            print(f"[{idx}/{n}] {pid}: FAILED - {exc}", flush=True)
            bump("failed")
            return
        (artifact_dir / f"{pid}.json").write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        st = artifact.get("status", "?")
        with lock:
            stats.statuses[st] = stats.statuses.get(st, 0) + 1
            stats.done += 1
        print(f"[{idx}/{n}] {pid}: {st}{describe(artifact)} ({time.time() - t0:.1f}s)", flush=True)

    if workers <= 1:
        for i, item in enumerate(items, 1):
            process(i, item)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(process, i, item) for i, item in enumerate(items, 1)]
            for fut in as_completed(futs):
                fut.result()

    stats.aborted = bool(breaker and breaker.tripped.is_set())
    return stats


def print_stats(stats: RunStats, seconds: float) -> None:
    by_status = ", ".join(f"{k}: {v}" for k, v in sorted(stats.statuses.items())) or "none"
    print(f"\nRun finished in {seconds:.0f}s — processed {stats.done} ({by_status}); "
          f"skipped (already finished): {stats.skipped}; crashed: {stats.failed}"
          + (f"; NOT STARTED (aborted): {stats.not_started}" if stats.aborted else ""), flush=True)
