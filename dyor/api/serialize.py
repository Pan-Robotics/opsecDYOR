"""JSON serializers — turn dataclasses/records into plain dicts for the API."""

from __future__ import annotations

import math
from typing import Any

from dyor.classes import FEATURE_DIRECTION, class_profile
from dyor.scoring.composite import ScoreResult


def _num(x: Any) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(x, 4) if isinstance(x, float) else x


def chart_summary(prices: list[list[float]], max_points: int = 150) -> dict[str, Any]:
    """Downsample a [[ms, price], ...] series and compute the period change.

    Always keeps the last point so the latest price is exact.
    """
    pts = [[p[0], p[1]] for p in (prices or []) if p and len(p) >= 2]
    if len(pts) > max_points:
        step = max(1, len(pts) // max_points)
        sampled = pts[::step]
        if sampled[-1] is not pts[-1]:
            sampled.append(pts[-1])
        pts = sampled
    first = pts[0][1] if pts else None
    last = pts[-1][1] if pts else None
    change = ((last - first) / first * 100) if (first not in (None, 0)) else None
    return {
        "prices": pts,
        "first": first,
        "last": last,
        "change_pct": round(change, 2) if change is not None else None,
    }


def score_to_dict(sr: ScoreResult) -> dict[str, Any]:
    return {
        "token": sr.token,
        "raw_score": _num(sr.raw_score),
        "final_score": _num(sr.final_score),
        "tier": sr.tier,
        "coverage": _num(sr.coverage),
        "features_present": sr.features_present,
        "features_total": sr.features_total,
        "tier_stability": _num(sr.tier_stability),
        "confidence": sr.confidence,
        "flags": list(sr.flags),
        "advisories": list(sr.advisories),
        "domain_scores": {k: _num(v) for k, v in sr.domain_scores.items()},
    }


def class_to_dict(name: str | None) -> dict[str, Any]:
    p = class_profile(name)
    return {"name": p.name, "label": p.label, "description": p.description,
            "domains": list(p.feature_spec.keys()),
            "required_domains": sorted(p.required_domains)}


def record_to_dict(rec: dict | None) -> dict[str, Any]:
    rec = rec or {}
    return {
        "features": {f: _num(rec.get(f)) for f in FEATURE_DIRECTION if rec.get(f) is not None},
        "market": rec.get("_market"),
        "categories": rec.get("_categories"),
        "feeds": rec.get("_feeds"),
        "contract_verified": rec.get("contract_verified"),
        "vc": {"num_backers": rec.get("num_vc_backers"),
               "had_public_sale": rec.get("had_public_sale")},
        "class": class_to_dict(rec.get("_class")),
    }


def resolved_to_dict(rt) -> dict[str, Any]:
    return {
        "name": rt.name, "symbol": rt.symbol, "gecko_id": rt.gecko_id,
        "matched_by": rt.matched_by, "market_cap_rank": rt.market_cap_rank,
        "chains": rt.chains, "platforms": rt.platforms,
        "explorers": rt.explorer_links(), "coingecko_url": rt.coingecko_url,
        "links": rt.links,
    }


def analyze_to_dict(res) -> dict[str, Any]:
    return {
        "query": res.query,
        "resolved": None if res.resolved is None else resolved_to_dict(res.resolved),
        "score": None if res.result is None else score_to_dict(res.result),
        "record": record_to_dict(res.record),
        "peer_count": res.peer_count,
        "rank": res.rank,
        "peers": [score_to_dict(r) for r in res.all_results],
        "errors": res.errors,
        "ok": res.ok,
    }
