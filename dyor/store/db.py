"""DuckDB-backed raw store.

ELT pattern: land raw JSON payloads first (immutable, source-of-truth), transform
later. DuckDB is ideal for a single-founder build — embedded, zero-ops, fast SQL
over JSON/parquet (Electric Capital's own tooling uses it).

Two core tables:
  raw_responses(source, key, fetched_at, payload)  — every API response, verbatim
  crosswalk(...)                                    — token identity (see identity/)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from dyor.config import PROJECT_ROOT

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "dyor.duckdb"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_responses (
    source     VARCHAR NOT NULL,
    key        VARCHAR NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    payload    JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS crosswalk (
    chain_address VARCHAR PRIMARY KEY,   -- canonical key, lowercase 'chain:0x..'
    chain         VARCHAR,
    address       VARCHAR,
    gecko_id      VARCHAR,               -- CoinGecko id (canonical entity)
    defillama_slug VARCHAR,              -- joined via gecko_id
    cmc_id        VARCHAR,
    symbol        VARCHAR,
    name          VARCHAR
);
CREATE TABLE IF NOT EXISTS token_records (
    run_id       VARCHAR NOT NULL,       -- groups one collection run
    collected_at TIMESTAMP NOT NULL,
    token        VARCHAR NOT NULL,
    record       JSON NOT NULL           -- the full computed scoring record
);
CREATE TABLE IF NOT EXISTS reference_records (
    asset_class  VARCHAR NOT NULL,       -- the class this basket represents
    token        VARCHAR NOT NULL,
    updated_at   TIMESTAMP NOT NULL,
    record       JSON NOT NULL
);
"""


def connect(path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open (and initialize) a DuckDB database. Use ':memory:' for tests."""
    db_path = path if path is not None else DEFAULT_DB_PATH
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        db_path = str(db_path)
    con = duckdb.connect(db_path)
    con.execute(_SCHEMA)
    return con


def land_raw(con: duckdb.DuckDBPyConnection, source: str, key: str, payload: Any) -> None:
    """Append one raw API response to `raw_responses`."""
    con.execute(
        "INSERT INTO raw_responses VALUES (?, ?, ?, ?)",
        [source, key, datetime.now(timezone.utc), json.dumps(payload)],
    )


def latest_raw(con: duckdb.DuckDBPyConnection, source: str, key: str) -> Any | None:
    """Most recent landed payload for (source, key), or None."""
    row = con.execute(
        """
        SELECT payload FROM raw_responses
        WHERE source = ? AND key = ?
        ORDER BY fetched_at DESC LIMIT 1
        """,
        [source, key],
    ).fetchone()
    return json.loads(row[0]) if row else None


def persist_records(con: duckdb.DuckDBPyConnection, records: list[dict[str, Any]]) -> str:
    """Persist one collection run of computed scoring records. Returns the run_id.

    Records are append-only and grouped by run_id (a UTC timestamp string) so the
    history is preserved and `latest_records` can pull the newest run.
    """
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    con.executemany(
        "INSERT INTO token_records VALUES (?, ?, ?, ?)",
        [[run_id, now, r.get("token"), json.dumps(r)] for r in records],
    )
    return run_id


def latest_records(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return the scoring records from the most recent collection run (or [])."""
    run = con.execute(
        "SELECT run_id FROM token_records ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()
    if not run:
        return []
    return records_for_run(con, run[0])


def upsert_into_latest_run(con: duckdb.DuckDBPyConnection, record: dict[str, Any]) -> str:
    """Refresh ONE token's record in the most recent run (live self-heal).

    When a token is analyzed live, write its fresh record back so the screener
    (which reads `latest_records`) agrees on next view — without spawning a new
    one-token run that would replace the whole universe. The row's timestamp is
    bumped to now but it stays under the latest run_id, so `latest_records` keeps
    returning the same (now-refreshed) universe. Bootstraps a run if empty.
    """
    token = record.get("token")
    now = datetime.now(timezone.utc)
    run = con.execute(
        "SELECT run_id FROM token_records ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()
    run_id = run[0] if run else now.strftime("%Y%m%dT%H%M%S%fZ")
    con.execute(
        "DELETE FROM token_records WHERE run_id = ? AND token = ?", [run_id, token]
    )
    con.execute(
        "INSERT INTO token_records VALUES (?, ?, ?, ?)",
        [run_id, now, token, json.dumps(record)],
    )
    return run_id


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


def upsert_crosswalk(con: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Replace-insert crosswalk rows. Returns the number written."""
    if not rows:
        return 0
    cols = ["chain_address", "chain", "address", "gecko_id",
            "defillama_slug", "cmc_id", "symbol", "name"]
    con.executemany(
        f"INSERT OR REPLACE INTO crosswalk ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)})",
        [[r.get(c) for c in cols] for r in rows],
    )
    return len(rows)
