"""Portfolio-level scoring + the thesis' "Barbell" builder.

Score a basket of holdings (concentration, class/narrative exposure, flagged
risks), and build a barbell: a monetary anchor (BTC) + a few high-conviction,
ungated satellites — directly the framework's portfolio-construction rule.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def score_portfolio(queries: list[str], config: dict | None = None,
                    *, peer_mode: str = "class") -> dict[str, Any]:
    """Analyze each holding and aggregate into a portfolio view."""
    from dyor.analyze import analyze_token

    holdings: list[dict[str, Any]] = []
    for q in queries[:25]:
        res = analyze_token(q, config, peer_mode=peer_mode)
        if res.resolved is None:
            holdings.append({"query": q, "error": "unresolved"})
            continue
        s = res.result
        holdings.append({
            "token": res.resolved.gecko_id, "name": res.resolved.name,
            "symbol": res.resolved.symbol,
            "class": (res.record or {}).get("_class"),
            "score": None if s is None else round(s.final_score, 4) if s.final_score == s.final_score else None,
            "tier": None if s is None else s.tier,
            "flags": [] if s is None else list(s.flags),
        })

    scored = [h for h in holdings if h.get("tier")]
    tiers = Counter(h["tier"].strip()[:1] for h in scored)
    classes = Counter(h["class"] for h in scored if h.get("class"))
    flagged = [h["symbol"] for h in scored if h["flags"]]
    valid_scores = [h["score"] for h in scored if h["score"] is not None]

    notes = []
    if not any(h.get("class") in ("monetary",) for h in scored):
        notes.append("No monetary anchor (BTC-like) — the thesis wants a store-of-value core.")
    sats = [h for h in scored if h.get("class") not in ("monetary", "stablecoin")]
    if len(sats) > 8:
        notes.append(f"{len(sats)} satellites — over-diversified; the barbell favors 3–5 high-conviction picks.")
    if tiers.get("D"):
        notes.append(f"{tiers['D']} holding(s) in tier D (avoid) — candidates to trim.")
    if flagged:
        notes.append(f"Gate-flagged: {', '.join(flagged)}.")

    return {
        "holdings": holdings,
        "scored": len(scored),
        "tier_distribution": dict(tiers),
        "class_exposure": dict(classes),
        "avg_score": round(sum(valid_scores) / len(valid_scores), 4) if valid_scores else None,
        "flagged": flagged,
        "notes": notes or ["Looks balanced against the barbell heuristic."],
        "disclaimer": "Research aid, not financial advice.",
    }


def barbell(config: dict | None = None, *, n_satellites: int = 5,
            candidates: list[dict] | None = None) -> dict[str, Any]:
    """Build a barbell: monetary anchor (BTC) + top-N ungated, qualified satellites
    from a candidate pool (defaults to the last saved universe)."""
    from dyor.analyze import analyze_token
    from dyor.pipeline import score_universe

    if candidates is None:
        from dyor.store import db
        con = db.connect()
        try:
            candidates = db.latest_records(con)
        finally:
            con.close()

    ranked = score_universe(candidates or [], config)
    by_token = {r.get("token"): r for r in (candidates or [])}
    sats = []
    for r in ranked:
        rec = by_token.get(r.token, {})
        if rec.get("_class") in ("monetary", "stablecoin"):
            continue
        if r.flags or r.tier.strip()[:1] not in ("A", "B"):
            continue
        sats.append({"token": r.token, "class": rec.get("_class"),
                     "score": round(r.final_score, 4), "tier": r.tier})
        if len(sats) >= n_satellites:
            break

    anchor_res = analyze_token("bitcoin", config, peer_mode="class")
    anchor_s = anchor_res.result
    anchor = {"token": "bitcoin", "tier": anchor_s.tier if anchor_s else None,
              "score": round(anchor_s.final_score, 4) if anchor_s else None}

    return {
        "anchor": anchor,
        "satellites": sats,
        "rationale": f"BTC monetary anchor + {len(sats)} qualified (A/B, ungated) satellites "
                     f"from a {len(candidates or [])}-token pool. Concentrate, don't over-diversify.",
        "disclaimer": "Research aid, not financial advice.",
    }
