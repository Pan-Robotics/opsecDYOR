"""In-memory background-job registry for screener rebuilds.

Collecting a universe takes ~20–30 minutes (rate-limited feeds), too long for a
synchronous request. `start_build` spawns a daemon thread that collects +
persists; the API polls `job_status` until done, then re-reads the store.

Guard rails (each one is a production incident that has already happened):
  * the built universe UNIONS the class reference baskets, so a rebuild can't
    drop BTC/ETH/memecoins/stablecoins from the public board;
  * the persist goes through the shrink guard (`db.persist_run`);
  * builds take the same cross-process lock as the cron wrapper, so two
    collectors can never run at once (independent rate-limit buckets → 429
    storm; concurrent persists → DuckDB lock collisions);
  * the endpoint that starts a build is admin-gated (see api/app.py).

Single-process, in-memory — fine for a single-instance deployment.
"""

from __future__ import annotations

import contextlib
import fcntl
import threading
import time
import uuid
from typing import Any

from dyor.config import collect_lock_path

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_MAX_TOP_N = 80
_MAX_JOBS_KEPT = 50


def _set(job_id: str, **fields: Any) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {}).update(fields)
        if len(_JOBS) > _MAX_JOBS_KEPT:  # keep the registry bounded
            for old in sorted(_JOBS, key=lambda k: _JOBS[k].get("started", 0))[:-_MAX_JOBS_KEPT]:
                _JOBS.pop(old, None)


def start_build(top_n: int, category: str | None = None) -> str:
    """Start a background universe collection. Returns a job id."""
    top_n = max(1, min(top_n, _MAX_TOP_N))
    job_id = uuid.uuid4().hex[:12]
    _set(job_id, status="running", top_n=top_n, category=category,
         started=time.time(), count=0, error=None)
    threading.Thread(target=_run_build, args=(job_id, top_n, category), daemon=True).start()
    return job_id


def _run_build(job_id: str, top_n: int, category: str | None) -> None:
    lock_path = collect_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_file:
        _run_build_locked(job_id, top_n, category, lock_file)


def _run_build_locked(job_id: str, top_n: int, category: str | None, lock_file) -> None:
    try:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _set(job_id, status="error", finished=time.time(),
                 error="a collection is already running (cron refresh or another build)")
            return

        from dyor.collect import Collector
        from dyor.store import db
        from dyor.universe import fetch_universe

        # include_baskets: a TVL-only rebuild replaced the 114-token pinned
        # universe with 31 tokens on 2026-09-11 (a visitor clicked the button).
        targets = fetch_universe(top_n=top_n, category=category, include_baskets=not category)
        _set(job_id, target_count=len(targets))
        with Collector() as collector:
            records = collector.collect(targets)
            errors = len(collector.errors)
        if not records:
            _set(job_id, status="error", error="collect returned no records", finished=time.time())
            return
        con = db.connect()
        try:
            run_id = db.persist_run(con, records)
        finally:
            con.close()
        _set(job_id, status="done", count=len(records), feed_errors=errors,
             run_id=run_id, finished=time.time())
    except Exception as exc:  # surface to the client
        _set(job_id, status="error", error=f"{type(exc).__name__}: {exc}",
             finished=time.time())
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def job_status(job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return {"status": "unknown"}
        out = dict(job)
    out["elapsed"] = round(time.time() - out["started"], 1) if "started" in out else None
    return out
