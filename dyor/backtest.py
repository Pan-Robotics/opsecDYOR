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


def backtest(config: dict | None = None, *, use_cache: bool = True) -> dict[str, Any]:
    from dyor.ingestion.coingecko import CoinGeckoClient
    from dyor.pipeline import score_universe
    from dyor.store import db

    con = db.connect()
    samples: list[tuple[str, str, float]] = []  # (tier_letter, token, entry_price)
    try:
        for run_id, _at in db.runs(con):
            recs = db.records_for_run(con, run_id)
            results = {r.token: r for r in score_universe(recs, config)}
            for rec in recs:
                tok = rec.get("token")
                res = results.get(tok)
                entry = (rec.get("_market") or {}).get("price")
                if res and entry and not math.isnan(res.final_score):
                    samples.append((res.tier.strip()[:1], tok, entry))
    finally:
        con.close()

    if not samples:
        return {"samples": 0, "note": "no persisted runs with prices yet — run `dyor collect --persist` over time"}

    tokens = sorted({t for _, t, _ in samples})
    with CoinGeckoClient(config, use_cache=use_cache) as cg:
        current = {m["id"]: m.get("current_price") for m in cg.markets(tokens)}

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
    return {
        "samples": len(samples),
        "tokens": len(tokens),
        "by_tier": out,
        "note": "forward return from each persisted run's entry price to now; "
                "short history = noisy. Schedule `dyor refresh` to accumulate signal.",
        "disclaimer": "Research aid, not financial advice.",
    }
