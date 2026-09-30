"""The working behind a score — every element and calculation on the token page.

`explain(record, result)` turns a collected record (with the raw figures the
collector kept in `_inputs`) and its ScoreResult into a ledger:

  features — for each feature of the token's class: the raw inputs and the feed
             they came from, the formula with those inputs named, the resulting
             value, its percentile against the class's reference basket, and its
             share of / contribution to the composite; a missing feature says why
  domains  — the roll-up: weight, weight renormalized over the domains present,
             mean of the scored features, contribution to the raw score
  gate     — every disqualifier rule with its evidence, whether it tripped, and
             the ceiling applied
  tier     — thresholds, the tier, its stability, and data coverage

This is a presentation module: score-like numbers come out on the 0–100
display scale (`scoring.composite.display`); raw inputs keep their own units.
Nothing here changes a score — it only shows how the pipeline arrived at it.
"""

from __future__ import annotations

import math
from typing import Any

from dyor.app.copy import DOMAIN_META, FEATURE_META
from dyor.classes import class_profile
from dyor.config import load_config
from dyor.feeds import FEATURE_SOURCE  # feature → feed, derived from FEED_FIELDS
from dyor.scoring.composite import ScoreResult, display
from dyor.scoring.gate import OPEN_DATA_ACTIVE

# Features that need a keyed / paid source even when the feed itself is on.
FEATURE_GATED: dict[str, str] = {
    "social_trend": "Santiment social volume needs DYOR_SANTIMENT_API_KEY",
    "unlock_overhang": "vesting data needs a CryptoRank Pro plan",
    "unlock_pct_of_volume": "next-unlock value needs CryptoRank Pro or DefiLlama Pro",
}

# The feature's own unit: x = multiple, ratio = 0–1 fraction (rendered as %), count.
FEATURE_UNIT: dict[str, str] = {
    "price_to_fees": "x", "price_to_sales": "x", "mc_tvl": "x", "fdv_mcap_ratio": "x",
    "unlock_pct_of_volume": "x",
    "real_yield": "ratio", "float_ratio": "ratio", "value_accrual": "ratio",
    "unlock_overhang": "ratio", "top10_concentration": "ratio", "social_sentiment": "ratio",
    "address_growth": "ratio", "dev_commit_trend": "ratio", "social_trend": "ratio",
    "watchlist_users": "count", "dev_activity": "per_day",
}


def _nan(x: Any) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _inp(key: str, label: str, value: Any, unit: str, source: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "unit": unit, "source": source}


def _annualized_inputs(name: str, label: str, d: dict | None) -> tuple[list[dict], str | None]:
    """Inputs + formula fragment for an annualized DefiLlama summary
    ({window, days, total, annualized} from collect.annualized_detail)."""
    if not d:
        return [], None
    total_key, days_key = f"{name}_total", f"{name}_days"
    inputs = [_inp(total_key, f"{label} ({d['window']})", d["total"], "usd", "defillama")]
    if d["days"] == 365:
        return inputs, f"{{{total_key}}}"
    inputs.append(_inp(days_key, "window days", d["days"], "days", "defillama"))
    return inputs, f"({{{total_key}}} × 365 ÷ {{{days_key}}})"


def _growth_inputs(name: str, label: str, d: dict | None, window_days: int | None) -> tuple[list[dict], str | None]:
    """Inputs + formula for a Santiment series growth (onchain.series_growth_detail)."""
    if not d:
        return [], None
    k = d["k"]
    inputs = [
        _inp(f"{name}_early", f"{label}, first {k}-day mean", d["early_mean"], "count", "santiment"),
        _inp(f"{name}_late", f"{label}, last {k}-day mean", d["late_mean"], "count", "santiment"),
        _inp(f"{name}_window", "window", window_days, "days", "santiment"),
    ]
    return inputs, f"({{{name}_late}} − {{{name}_early}}) ÷ {{{name}_early}}"


def feature_working(feature: str, inputs: dict[str, Any] | None) -> tuple[list[dict], str | None]:
    """(inputs, formula) for one feature from the record's `_inputs`.

    The formula names inputs as `{key}`; the UI substitutes formatted values so
    "$3.4B ÷ ($214K × 365 ÷ 30)" reads next to the result. Empty when the
    inputs the feature needs were never collected.
    """
    i = inputs or {}
    mc = _inp("market_cap", "Market cap", i.get("market_cap"), "usd", "coingecko")
    circ = _inp("circulating_supply", "Circulating supply", i.get("circulating_supply"), "count", "coingecko")
    total = _inp("total_supply", "Total supply", i.get("total_supply"), "count", "coingecko")

    if feature == "price_to_fees":
        ins, frag = _annualized_inputs("fees", "Fees", i.get("fees"))
        return ([mc, *ins], f"{{market_cap}} ÷ {frag}") if frag else ([], None)
    if feature == "price_to_sales":
        ins, frag = _annualized_inputs("revenue", "Revenue", i.get("revenue"))
        return ([mc, *ins], f"{{market_cap}} ÷ {frag}") if frag else ([], None)
    if feature == "mc_tvl":
        if i.get("tvl") is None:
            return [], None
        return [mc, _inp("tvl", "TVL", i.get("tvl"), "usd", "defillama")], "{market_cap} ÷ {tvl}"
    if feature == "real_yield":
        ins, frag = _annualized_inputs("holders_revenue", "Holders revenue", i.get("holders_revenue"))
        return ([*ins, mc], f"{frag} ÷ {{market_cap}}") if frag else ([], None)
    if feature == "fdv_mcap_ratio":
        if i.get("fdv_mcap_method") == "fdv_over_mcap":
            return [_inp("fdv", "FDV", i.get("fdv"), "usd", "coingecko"), mc], "{fdv} ÷ {market_cap}"
        if i.get("fdv_mcap_method") is None:
            return [], None
        return [total, circ], "{total_supply} ÷ {circulating_supply}"
    if feature == "float_ratio":
        if i.get("circulating_supply") is None or i.get("total_supply") is None:
            return [], None
        return [circ, total], "{circulating_supply} ÷ {total_supply}"
    if feature == "value_accrual":
        w = i.get("value_accrual_window") or {}
        if not w.get("window"):
            return [], None
        return ([_inp("va_holders", f"Holders revenue ({w['window']})", w.get("holders_revenue"), "usd", "defillama"),
                 _inp("va_revenue", f"Revenue ({w['window']})", w.get("revenue"), "usd", "defillama")],
                "{va_holders} ÷ {va_revenue}")
    if feature == "unlock_overhang":
        u = i.get("unlock") or {}
        if u.get("has_vesting") is None:
            return [], None
        ins = [_inp("available_supply", "Available supply", u.get("available_supply"), "count", "cryptorank"),
               _inp("max_supply", "Max supply", u.get("max_supply"), "count", "cryptorank"),
               _inp("has_vesting", "Vesting schedule", u.get("has_vesting"), "bool", "cryptorank")]
        return ins, ("1 − {available_supply} ÷ {max_supply}" if u.get("has_vesting") else "0 — no vesting schedule")
    if feature == "unlock_pct_of_volume":
        u = i.get("unlock") or {}
        if u.get("next_unlock_usd") is None:
            return [], None
        return ([_inp("next_unlock_usd", "Next unlock", u.get("next_unlock_usd"), "usd", "cryptorank"),
                 _inp("volume_24h", "24h volume", i.get("volume_24h"), "usd", "coingecko")],
                "{next_unlock_usd} ÷ {volume_24h}")
    if feature == "top10_concentration":
        shares = i.get("top10_shares_pct")
        if not shares:
            return [], None
        return [_inp("top10_shares", "Top-10 holder shares", shares, "pct_list", "ethplorer")], "Σ {top10_shares}"

    san = i.get("santiment") or {}
    if feature == "address_growth":
        return _growth_inputs("daa", "Daily active addresses", san.get("daily_active_addresses"), san.get("window_days"))
    if feature == "dev_commit_trend":
        return _growth_inputs("dev", "Dev-activity events", san.get("dev_activity"), san.get("window_days"))
    if feature == "dev_activity":
        d = san.get("dev_activity") or {}
        if d.get("events") is None or not d.get("n"):
            return [], None
        return ([_inp("dev_events", "Dev-activity events in window", d["events"], "count", "santiment"),
                 _inp("dev_days", "days with data", d["n"], "days", "santiment")],
                "{dev_events} ÷ {dev_days}")
    if feature == "social_trend":
        return _growth_inputs("social", "Social volume", san.get("social_volume"), san.get("window_days"))
    if feature == "social_sentiment":
        v = i.get("sentiment_votes_up_pct")
        return ([_inp("votes_up", "Community up-votes", v, "pct", "coingecko")], "{votes_up} ÷ 100") if v is not None else ([], None)
    if feature == "watchlist_users":
        v = i.get("watchlist_users")
        return ([_inp("watchlist", "CoinGecko watchlists", v, "count", "coingecko")], "{watchlist}") if v is not None else ([], None)
    return [], None


def missing_reason(feature: str, value: Any, feeds: dict[str, str] | None) -> str:
    """Why a feature has no percentile — the feed, a keyed source, or the math."""
    src = FEATURE_SOURCE.get(feature)
    status = (feeds or {}).get(src) if src else None
    gated = FEATURE_GATED.get(feature)
    if value is not None:
        return "value collected but no reference basket carries this feature — left out rather than ranked against the ad-hoc peer set"
    if status == "error":
        return f"{src} errored this run"
    if status == "off":
        return gated or f"{src} feed off — no identifier for this token"
    if status == "empty":
        return gated or f"{src} has no data for this token"
    if status == "ok":
        return gated or f"{src} responded but the ratio is undefined (zero denominator or no shared window)"
    return gated or "no data"


def explain(record: dict | None, result: ScoreResult | None, config: dict | None = None) -> dict[str, Any] | None:
    """The full ledger for one scored token (see module docstring). None when
    there is no score to explain."""
    if result is None:
        return None
    cfg = config if config is not None else load_config()
    rec = record or {}
    profile = class_profile(rec.get("_class"), cfg)
    inputs = rec.get("_inputs") or {}
    feeds = rec.get("_feeds") or {}
    weights = dict(profile.weights)
    dscores = dict(result.domain_scores)

    present_domains = {d for d, s in dscores.items() if d in weights and not _nan(s)}
    total_w = sum(weights[d] for d in present_domains)

    # --- domains -------------------------------------------------------------
    domains: list[dict[str, Any]] = []
    for d, feats in profile.feature_spec.items():
        names = [f for f, _ in feats]
        scored = [f for f in names if f in result.feature_scores and not _nan(result.feature_scores[f])]
        s = dscores.get(d)
        present = d in present_domains
        w = weights.get(d, 0.0)
        wn = (w / total_w) if (present and total_w) else None
        label, desc = DOMAIN_META.get(d, (d, ""))
        domains.append({
            "domain": d, "label": label, "description": desc,
            "weight": round(w, 4),
            "weight_renormalized": None if wn is None else round(wn, 4),
            "features_total": len(names), "features_scored": len(scored),
            "score": display(s) if present else None,
            "penalized": bool(present and not scored),  # floored by the core-domain penalty
            "required": d in profile.required_domains,
            "contribution": display(wn * s) if (wn is not None and not _nan(s)) else None,
        })

    # --- features ------------------------------------------------------------
    features: list[dict[str, Any]] = []
    for d, feats in profile.feature_spec.items():
        n_scored = sum(1 for f, _ in feats if f in result.feature_scores and not _nan(result.feature_scores[f]))
        wd = weights.get(d, 0.0)
        for f, higher in feats:
            label, meaning, _ = FEATURE_META.get(f, (f, "", ""))
            ins, formula = feature_working(f, inputs)
            value = rec.get(f)
            pct = result.feature_scores.get(f)
            scored = not _nan(pct)
            share = (wd / total_w / n_scored) if (scored and total_w and n_scored) else None
            src = FEATURE_SOURCE.get(f)
            features.append({
                "feature": f, "label": label, "meaning": meaning, "domain": d,
                "direction": "higher is better" if higher else "lower is better",
                "source": src, "feed_status": feeds.get(src) if src else None,
                "inputs": ins, "formula": formula,
                "value": None if _nan(value) else value, "unit": FEATURE_UNIT.get(f),
                "percentile": display(pct) if scored else None,
                "reference_n": result.feature_ref_n.get(f),
                "weight": None if share is None else round(share * 100, 2),        # % of the composite
                "contribution": display(share * pct) if share is not None else None,  # points of the raw score
                "status": "scored" if scored else "missing",
                "missing_reason": None if scored else missing_reason(f, None if _nan(value) else value, feeds),
            })

    # --- gate ----------------------------------------------------------------
    rules = cfg["gating"]["rules"]
    crit = cfg["gating"].get("dead_token", {})
    flags = set(result.flags)
    gh = inputs.get("github_account") or rec.get("_github_account")

    def ev(label: str, value: Any, unit: str, threshold: str | None = None) -> dict[str, Any]:
        return {"label": label, "value": None if _nan(value) else value, "unit": unit, "threshold": threshold}

    evidence: dict[str, list[dict[str, Any]]] = {
        "unverified_contract": [ev("Contract verified (Sourcify)", rec.get("contract_verified"), "bool", "trips when False")],
        "anonymous_team": [ev("Team anonymous", rec.get("team_anonymous"), "bool", "trips when True")],
        "no_audit": [ev("Audit on record (DefiLlama)", rec.get("audited"), "bool", "trips when False")],
        "extreme_fdv_mcap": [ev("FDV / MCAP", rec.get("fdv_mcap_ratio"), "x",
                                f"trips when > {rules.get('extreme_fdv_mcap', {}).get('threshold', 10.0):g}×")],
        "dead_token": [
            ev("Days since last GitHub push" + (f" ({gh})" if gh else ""), rec.get("days_since_last_commit"),
               "days", f"trips at ≥ {crit.get('no_commits_days', 180)} days"),
            ev("Santiment dev events in window", rec.get("dev_activity_events"), "count", "> 0 overrules a stale GitHub org"),
            ev("24h volume", rec.get("daily_volume_usd"), "usd", f"trips below ${crit.get('min_daily_volume_usd', 1000.0):,.0f}"),
        ],
    }
    gate_rows = [{
        "rule": name,
        "action": r.get("action"),
        "cap": display(r.get("cap")) if r.get("cap") is not None else (0.0 if r.get("action") == "zero" else None),
        "active_on_open_data": name in OPEN_DATA_ACTIVE,
        "tripped": name in flags,
        "evidence": evidence.get(name, []),
    } for name, r in rules.items()]
    gate = {
        "rules": gate_rows,
        "flags": sorted(flags),
        "cap": display(result.gate_cap) if result.gate_cap is not None else None,
        "raw_score": display(result.raw_score),
        "final_score": display(result.final_score),
    }

    # --- tier ----------------------------------------------------------------
    tiers = sorted(cfg["scoring"]["tiers"], key=lambda t: t["min"], reverse=True)
    tier = {
        "tier": result.tier,
        "thresholds": [{"label": t["label"], "min": display(t["min"], 0)} for t in tiers],
        "stability": display(result.tier_stability, 0),
        "confidence": result.confidence,
        "coverage": {"present": result.features_present, "total": result.features_total,
                     "pct": display(result.coverage, 0)},
    }

    method = {
        "class": profile.name, "class_label": profile.label,
        "normalization": cfg["scoring"]["normalization"],
        "reference_anchored": bool(cfg["scoring"].get("reference_anchored", False)),
        "penalize_missing_core": bool(cfg["scoring"].get("penalize_missing_core", True)),
        "missing_core_penalty": display(cfg["scoring"].get("missing_core_penalty", 0.0)),
        "scale": 100,
    }
    return {"method": method, "features": features, "domains": domains, "gate": gate, "tier": tier}
