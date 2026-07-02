"""Programmatic screening — filter a scored universe by criteria.

Lets an agent (or the CLI/API) ask "DeFi, tier B+, real-yield > 4.5%, no unlock
overhang, verified contract" instead of eyeballing the screener. Pure on top of
the scored records, so it's testable offline.
"""

from __future__ import annotations

from typing import Any

from dyor.pipeline import score_universe

_TIER_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}


def screen(
    records: list[dict],
    config: dict | None = None,
    *,
    asset_class: str | None = None,
    min_tier: str | None = None,      # e.g. "B" → A or B
    min_score: float | None = None,
    min_coverage: float | None = None,
    no_flags: bool = False,
    feature_min: dict[str, float] | None = None,   # {"real_yield": 0.045}
    feature_max: dict[str, float] | None = None,   # {"fdv_mcap_ratio": 3}
    peer_groups: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Score `records` and return those passing every criterion, ranked high→low."""
    by_token = {r.get("token"): r for r in records}
    results = score_universe(records, config, peer_groups=peer_groups)
    max_tier_rank = _TIER_RANK.get((min_tier or "").strip()[:1], 99)

    out: list[dict[str, Any]] = []
    for r in results:
        rec = by_token.get(r.token, {})
        if asset_class and rec.get("_class") != asset_class:
            continue
        if min_tier and _TIER_RANK.get(r.tier.strip()[:1], 99) > max_tier_rank:
            continue
        if min_score is not None and (r.final_score != r.final_score or r.final_score < min_score):
            continue
        if min_coverage is not None and (r.coverage != r.coverage or r.coverage < min_coverage):
            continue
        if no_flags and r.flags:
            continue
        if feature_min and any(
            rec.get(f) is None or rec.get(f) < v for f, v in feature_min.items()):
            continue
        if feature_max and any(
            rec.get(f) is None or rec.get(f) > v for f, v in feature_max.items()):
            continue
        out.append({
            "token": r.token,
            "class": rec.get("_class"),
            "score": None if r.final_score != r.final_score else round(r.final_score, 4),
            "tier": r.tier,
            "coverage": None if r.coverage != r.coverage else round(r.coverage, 3),
            "confidence": r.confidence,
            "flags": list(r.flags),
        })
    return out[:limit] if limit else out
