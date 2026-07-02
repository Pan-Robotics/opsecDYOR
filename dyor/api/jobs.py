"""In-memory background-job registry for long screener builds.

Collecting a top-N universe takes minutes (rate-limited feeds), too long for a
synchronous request. `start_build` spawns a daemon thread that collects +
persists; the API polls `job_status` until done, then re-reads the store.

Single-process, in-memory — fine for a local/single-instance tool. For
multi-worker deployment, back this with Redis or a real task queue.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_MAX_TOP_N = 80


def _set(job_id: str, **fields: Any) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {}).update(fields)


def start_build(top_n: int, category: str | None = None) -> str:
    """Start a background universe collection. Returns a job id."""
    top_n = max(1, min(top_n, _MAX_TOP_N))
    job_id = uuid.uuid4().hex[:12]
    _set(job_id, status="running", top_n=top_n, category=category,
         started=time.time(), count=0, error=None)
    threading.Thread(target=_run_build, args=(job_id, top_n, category), daemon=True).start()
    return job_id


def _run_build(job_id: str, top_n: int, category: str | None) -> None:
    try:
        from dyor.collect import Collector
        from dyor.store import db
        from dyor.universe import fetch_universe

        targets = fetch_universe(top_n=top_n, category=category)
        _set(job_id, target_count=len(targets))
        with Collector() as collector:
            records = collector.collect(targets)
            errors = len(collector.errors)
        con = db.connect()
        run_id = db.persist_records(con, records)
        con.close()
        # New universe → recalibrate the reference distributions on next use.
        from dyor.reference import clear_distribution_cache
        clear_distribution_cache()
        _set(job_id, status="done", count=len(records), feed_errors=errors,
             run_id=run_id, finished=time.time())
    except Exception as exc:  # noqa: BLE001 — surface to the client
        _set(job_id, status="error", error=f"{type(exc).__name__}: {exc}",
             finished=time.time())


def job_status(job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return {"status": "unknown"}
        out = dict(job)
    out["elapsed"] = round(time.time() - out["started"], 1) if "started" in out else None
    return out
