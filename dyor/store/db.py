"""DuckDB-backed store for collection runs and reference baskets.

Two tables:
  token_records(run_id, collected_at, token, record)       — one row per token
      per collection run; the screener reads the newest run.
  reference_records(asset_class, token, updated_at, record) — the curated
      per-class baskets that anchor scoring (see dyor/reference.py).

DuckDB is single-writer ACROSS PROCESSES: a second process cannot open the file
read-write at all. Readers therefore open `read_only=True` (which also skips
the DDL), and writers keep their connection for as short a window as possible.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from dyor.config import PROJECT_ROOT, load_config

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "dyor.duckdb"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS token_records (
    run_id       VARCHAR NOT NULL,       -- groups one collection run
    collected_at TIMESTAMP NOT NULL,
    token        VARCHAR NOT NULL,
    record       JSON NOT NULL           -- the full computed scoring record
);
CREATE INDEX IF NOT EXISTS idx_token_records_run ON token_records(run_id);
CREATE INDEX IF NOT EXISTS idx_token_records_at  ON token_records(collected_at);
CREATE TABLE IF NOT EXISTS reference_records (
    asset_class  VARCHAR NOT NULL,       -- the class this basket represents
    token        VARCHAR NOT NULL,
    updated_at   TIMESTAMP NOT NULL,
    record       JSON NOT NULL
);
"""


class RunShrinkRefused(RuntimeError):
    """Persisting this run would replace the screener's universe with a much
    smaller one. Raised instead of silently shrinking the public board."""


def connect(path: str | Path | None = None, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB database. Use ':memory:' for tests.

    `read_only=True` opens without the write lock (other read-only openers can
    coexist) and skips schema DDL; it falls back to a normal open when the file
    does not exist yet so first-run readers still see empty tables.
    """
    db_path = path if path is not None else DEFAULT_DB_PATH
    if db_path == ":memory:":
        con = duckdb.connect(db_path)
        con.execute(_SCHEMA)
        return con
    p = Path(db_path)
    if read_only and p.exists():
        return duckdb.connect(str(p), read_only=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(p))
    con.execute(_SCHEMA)
    return con


# --- collection runs ------------------------------------------------------------

def _new_run_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S%fZ")


def persist_records(con: duckdb.DuckDBPyConnection, records: list[dict[str, Any]]) -> str:
    """Append one collection run (no size check). Returns the run_id.

    Prefer `persist_run`, which refuses to shrink the universe; this is the raw
    primitive for tests and deliberate one-off writes.
    """
    now = datetime.now(timezone.utc)
    run_id = _new_run_id(now)
    con.executemany(
        "INSERT INTO token_records VALUES (?, ?, ?, ?)",
        [[run_id, now, r.get("token"), json.dumps(r)] for r in records],
    )
    return run_id


def persist_run(
    con: duckdb.DuckDBPyConnection,
    records: list[dict[str, Any]],
    *,
    config: dict | None = None,
    force: bool = False,
) -> str:
    """Persist a run as the new latest universe, refusing a drastic shrink.

    The screener reads only the newest run, so a small run silently replaces the
    whole board — a top-30 rebuild and a `dyor refresh` with no `--top-n` (the
    6-token curated set) both did this in production. Below
    `store.min_run_fraction` of the previous run, raise `RunShrinkRefused`
    unless `force=True`.
    """
    cfg = config if config is not None else load_config()
    min_fraction = float(cfg.get("store", {}).get("min_run_fraction", 0.5))
    prev = latest_records(con)
    if prev and not force and len(records) < len(prev) * min_fraction:
        raise RunShrinkRefused(
            f"refusing to persist {len(records)} tokens over a {len(prev)}-token run "
            f"(< {min_fraction:.0%}); pass force=True / --force if this is intended"
        )
    return persist_records(con, records)


def latest_records(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return the scoring records from the most recent collection run (or [])."""
    run = con.execute(
        "SELECT run_id FROM token_records ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()
    if not run:
        return []
    return records_for_run(con, run[0])


def token_in_latest_run(con: duckdb.DuckDBPyConnection, token: str) -> bool:
    run = con.execute(
        "SELECT run_id FROM token_records ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()
    if not run:
        return False
    row = con.execute(
        "SELECT 1 FROM token_records WHERE run_id = ? AND token = ? LIMIT 1", [run[0], token]
    ).fetchone()
    return row is not None


def upsert_into_latest_run(con: duckdb.DuckDBPyConnection, record: dict[str, Any]) -> str:
    """Write ONE token's record into the most recent run, adding it if absent.

    Operator primitive. The public API uses `refresh_in_latest_run`, which only
    refreshes tokens already on the board — otherwise any visitor's analysis
    would insert arbitrary tokens into the public screener.
    """
    token = record.get("token")
    now = datetime.now(timezone.utc)
    run = con.execute(
        "SELECT run_id FROM token_records ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()
    run_id = run[0] if run else _new_run_id(now)
    con.execute(
        "DELETE FROM token_records WHERE run_id = ? AND token = ?", [run_id, token]
    )
    con.execute(
        "INSERT INTO token_records VALUES (?, ?, ?, ?)",
        [run_id, now, token, json.dumps(record)],
    )
    return run_id


def _feeds_regressed(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """True when the fresh record's feeds ERRORED where the stored one's did not."""
    old_err = {k for k, v in (old.get("_feeds") or {}).items() if v == "error"}
    new_err = {k for k, v in (new.get("_feeds") or {}).items() if v == "error"}
    return bool(new_err - old_err)


def refresh_in_latest_run(con: duckdb.DuckDBPyConnection, record: dict[str, Any]) -> bool:
    """Live self-heal: replace a token's row in the latest run IF it is already
    there. Returns False (and writes nothing) for a token not on the board.

    Also refuses to replace a row with a WORSE one: a fresh record whose feeds
    errored where the stored one's did not (Santiment's monthly budget spent,
    a GitHub outage) would erase good features from the board and move the
    token's score for a reason that has nothing to do with the token. The
    transient failure is simply retried by the next analysis or refresh."""
    token = record.get("token")
    if not token:
        return False
    run = con.execute(
        "SELECT run_id FROM token_records ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()
    if not run:
        return False
    row = con.execute(
        "SELECT record FROM token_records WHERE run_id = ? AND token = ? LIMIT 1", [run[0], token]
    ).fetchone()
    if row is None:
        return False
    if _feeds_regressed(json.loads(row[0]), record):
        return False
    upsert_into_latest_run(con, record)
    return True


def runs(con: duckdb.DuckDBPyConnection) -> list[tuple[str, Any]]:
    """All collection runs as (run_id, collected_at), oldest first."""
    return con.execute(
        "SELECT run_id, MIN(collected_at) AS first_at FROM token_records "
        "GROUP BY run_id ORDER BY first_at"
    ).fetchall()


def records_for_run(con: duckdb.DuckDBPyConnection, run_id: str) -> list[dict[str, Any]]:
    """All token records landed under one run_id."""
    rows = con.execute(
        "SELECT record FROM token_records WHERE run_id = ?", [run_id]
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def prune_runs(con: duckdb.DuckDBPyConnection, keep: int) -> int:
    """Delete all but the newest `keep` runs. Returns rows removed.

    History is append-only and feeds the backtest, so keep plenty (the default
    `store.keep_runs` is three years of weekly runs) — but not forever.
    """
    all_runs = [rid for rid, _ in runs(con)]
    if keep < 1 or len(all_runs) <= keep:
        return 0
    stale = all_runs[: len(all_runs) - keep]
    before = con.execute("SELECT COUNT(*) FROM token_records").fetchone()[0]
    con.executemany("DELETE FROM token_records WHERE run_id = ?", [[r] for r in stale])
    after = con.execute("SELECT COUNT(*) FROM token_records").fetchone()[0]
    return before - after


# --- reference baskets ----------------------------------------------------------

def upsert_reference(con: duckdb.DuckDBPyConnection, asset_class: str,
                     records: list[dict[str, Any]]) -> int:
    """Replace the cached reference basket for one asset class."""
    con.execute("DELETE FROM reference_records WHERE asset_class = ?", [asset_class])
    if not records:
        return 0
    now = datetime.now(timezone.utc)
    con.executemany(
        "INSERT INTO reference_records VALUES (?, ?, ?, ?)",
        [[asset_class, r.get("token"), now, json.dumps(r)] for r in records],
    )
    return len(records)


def reference_records(con: duckdb.DuckDBPyConnection, asset_class: str) -> list[dict[str, Any]]:
    """Cached reference-basket records for one asset class (or [])."""
    rows = con.execute(
        "SELECT record FROM reference_records WHERE asset_class = ?", [asset_class]
    ).fetchall()
    return [json.loads(r[0]) for r in rows]
