"""Lightweight backtest — does the tier predict forward returns?

Uses persisted collection runs (each record stores its price at collection time)
+ current CoinGecko prices to compute forward return per tier. This is the
trust-building question — "did A/B-tier tokens outperform D?" — though with only a
few days of persisted runs the sample is small and noisy. The mechanism is the
deliverable; it compounds as runs accumulate (schedule `dyor refresh`).
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


import threading
import time

# One result per board version for a while: scoring every persisted run per click is
# heavy, and the answer only changes when a run is added or prices move materially.
_CACHE: dict[str, Any] = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SEC = 600


def _load_samples(config: dict | None) -> tuple[list[tuple[str, str, float]], str]:
    """(tier letter, token, entry price) for every record of every persisted run, plus a version key.

    The database connection is read-only and is CLOSED before any scoring happens:
    scoring opens its own read-only connections for the reference anchor, and DuckDB
    refuses a second connection with a different configuration in one process. Holding a
    read-write handle across `score_universe` is exactly what used to 503 this endpoint.
    """
    from dyor.pipeline import score_universe
    from dyor.store import db

    con = db.connect(read_only=True)
    runs: list[tuple[str, list[dict[str, Any]]]] = []
    try:
        for run_id, _at in db.runs(con):
            runs.append((run_id, db.records_for_run(con, run_id)))
    finally:
        con.close()

    samples: list[tuple[str, str, float]] = []
    for _run_id, recs in runs:
        results = {r.token: r for r in score_universe(recs, config)}
        for rec in recs:
            tok = rec.get("token")
            res = results.get(tok)
            entry = (rec.get("_market") or {}).get("price")
            if res and entry and not math.isnan(res.final_score):
                samples.append((res.tier.strip()[:1], tok, entry))
    version = ",".join(run_id for run_id, _ in runs)
    return samples, version


def backtest(config: dict | None = None, *, use_cache: bool = True) -> dict[str, Any]:
    from dyor.ingestion.coingecko import CoinGeckoClient

    if use_cache:
        with _CACHE_LOCK:
            hit = _CACHE.get("result")
            if hit and time.time() - hit["at"] < CACHE_TTL_SEC:
                return hit["value"]

    samples, _version = _load_samples(config)

    if not samples:
        return {"samples": 0, "note": "no persisted runs with prices yet; run `dyor collect --persist` over time"}

    tokens = sorted({t for _, t, _ in samples})
    current: dict[str, float | None] = {}
    price_errors: list[str] = []
    with CoinGeckoClient(config, use_cache=use_cache) as cg:
        # Chunked so one rejected call (rate limit) costs a slice of the prices, not the whole answer.
        for i in range(0, len(tokens), 50):
            part = tokens[i:i + 50]
            try:
                current.update({m["id"]: m.get("current_price") for m in cg.markets(part)})
            except Exception as exc:  # a price-service hiccup must not fail the page
                price_errors.append(f"{type(exc).__name__}: {str(exc)[:120]}")
    if not current:
        return {
            "samples": len(samples), "tokens": len(tokens), "by_tier": {},
            "note": "current prices unavailable right now (the price service rate-limited the request); try again in a minute.",
            "price_errors": price_errors[:3],
        }

    by_tier: dict[str, list[float]] = defaultdict(list)
    for letter, tok, entry in samples:
        cur = current.get(tok)
        if cur and entry:
            by_tier[letter].append((cur - entry) / entry)

    out: dict[str, Any] = {}
    for letter in "ABCD":
        rs = by_tier.get(letter, [])
        if rs:
            out[letter] = {
                "n": len(rs),
                "avg_return": round(sum(rs) / len(rs), 4),
                "win_rate": round(sum(1 for r in rs if r > 0) / len(rs), 3),
            }
    priced = sum(1 for t in tokens if current.get(t))
    result: dict[str, Any] = {
        "samples": len(samples),
        "tokens": len(tokens),
        "priced_tokens": priced,
        "by_tier": out,
        "note": "forward return from each persisted run's entry price to now; "
                "short history = noisy. Schedule `dyor refresh` to accumulate signal."
                + (f" {len(tokens) - priced} token(s) had no current price this time." if priced < len(tokens) else ""),
        "disclaimer": "Research aid, not financial advice.",
    }
    if price_errors:
        result["price_errors"] = price_errors[:3]
    if use_cache:
        with _CACHE_LOCK:
            _CACHE["result"] = {"at": time.time(), "value": result}
    return result
