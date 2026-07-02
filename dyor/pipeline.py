"""Scoring pipeline — turn a universe of token feature records into ranked scores.

This is the glue that enforces the cardinal rule: features are normalized
*across the peer set* (so percentile rank is meaningful) BEFORE they're combined
into domain scores and then a composite. Layers below stay peer-agnostic and
unit-testable; this module owns the cross-sectional step.

A token "record" is a flat dict of raw feature values plus the gate flags, e.g.:
    {
      "token": "hyperliquid",
      "price_to_fees": 12.4, "price_to_sales": 18.0, "mc_tvl": 2.1,
      "real_yield": 0.06, "fdv_mcap_ratio": 1.3,
      "unlock_pct_of_volume": 0.4, "float_ratio": 0.33, "inflation_rate": 0.05,
      "top10_concentration": 0.22, "address_growth": 0.12, "reserve_trend": -0.4,
      "social_trend": 0.3, "dev_commit_trend": 0.5,
      # gate inputs:
      "contract_verified": True, "team_anonymous": False, "audited": True,
      "days_since_last_commit": 3, "drawdown_from_ath_pct": 20.0,
      "daily_volume_usd": 5.0e8,
    }
Missing features are fine — they're skipped and weights renormalize.
"""

from __future__ import annotations

import numpy as np

from dyor.classes import FEATURE_DIRECTION, FEATURE_SPECS, ClassProfile, class_profile
from dyor.config import load_config
from dyor.scoring import normalize as norm
from dyor.scoring.composite import ScoreResult, score_token
from dyor.scoring.weights import Weights

# Back-compat: the default (general/DeFi) spec, used by the UI glossary.
FEATURE_SPEC: dict[str, list[tuple[str, bool]]] = FEATURE_SPECS["general"]

DOMAIN_LABEL = {"fundamental": "fundamentals", "tokenomics": "tokenomics",
                "onchain": "on-chain", "social": "social", "dev": "developer"}


def _normalized_features(
    records: list[dict],
    method: str,
    groups: list | None = None,
    ref_dist: dict[str, dict[str, np.ndarray]] | None = None,
) -> dict[str, np.ndarray]:
    """Normalize every feature column (the union across all classes) → {feature: array}.

    Each feature is normalized across ALL tokens that have it, so e.g. a DeFi
    token's P/F is ranked against other tokens with a P/F (monetary/meme tokens
    have None and don't participate). With `groups`, normalization happens within
    each peer group ("compare within category").

    When `ref_dist` is given ({class: {feature: reference array}}), a token's
    feature is instead ranked against its *class's fixed reference distribution*
    (percentile-of-score) — making the result independent of the ad-hoc peer set.
    Features/classes with no reference data fall back to the relative column above.
    """
    n = len(records)
    if groups is None:
        index_sets = [list(range(n))]
    else:
        buckets: dict = {}
        for i, g in enumerate(groups):
            buckets.setdefault(g, []).append(i)
        index_sets = list(buckets.values())

    out: dict[str, np.ndarray] = {}
    for feature, higher_is_better in FEATURE_DIRECTION.items():
        raw = [r.get(feature) for r in records]
        if all(v is None or (isinstance(v, float) and np.isnan(v)) for v in raw):
            continue
        full = np.full(n, np.nan)
        for idx in index_sets:
            col = [np.nan if raw[i] is None else raw[i] for i in idx]
            normed = norm.normalize(col, method=method, higher_is_better=higher_is_better)
            for j, i in enumerate(idx):
                full[i] = normed[j]
        out[feature] = full

    if ref_dist:
        _apply_reference_normalization(records, out, ref_dist)
    return out


def _apply_reference_normalization(
    records: list[dict],
    out: dict[str, np.ndarray],
    ref_dist: dict[str, dict[str, np.ndarray]],
) -> None:
    """Overlay fixed per-class reference percentiles onto the relative columns in
    `out`, in place.

    For a token whose class is *anchored* (has a non-empty reference basket), each
    feature is set to its percentile-of-score against the frozen basket — or
    excluded (NaN) when the basket has no distribution for it. Crucially we do NOT
    fall back to the relative value for an anchored class, because that relative
    value depends on the ad-hoc peer set and would reintroduce the very drift this
    fixes. Tokens of an *unanchored* class (no basket, e.g. "general") keep their
    relative column untouched.
    """
    for feature, higher_is_better in FEATURE_DIRECTION.items():
        col: np.ndarray | None = None
        for i, rec in enumerate(records):
            dist = ref_dist.get(rec.get("_class"))
            if not dist:  # unanchored class → leave the relative value in place
                continue
            if col is None:  # start from the relative column (preserves unanchored idxs)
                base = out.get(feature)
                col = base.copy() if base is not None else np.full(len(records), np.nan)
            raw = rec.get(feature)
            refvals = dist.get(feature)
            if (raw is None or (isinstance(raw, float) and np.isnan(raw))
                    or refvals is None or len(refvals) == 0):
                col[i] = np.nan  # no fixed basis → exclude (don't leak the peer set)
            else:
                col[i] = norm.percentile_of_score(raw, refvals, higher_is_better)
        if col is not None:
            out[feature] = col


def _domain_scores(
    norm_features: dict[str, np.ndarray], i: int, profile: ClassProfile
) -> dict[str, float]:
    """Average the present normalized features per domain, using the token's
    asset-class spec (so a monetary asset has no 'fundamental' domain at all)."""
    scores: dict[str, float] = {}
    for domain, feats in profile.feature_spec.items():
        vals = [
            norm_features[f][i]
            for f, _ in feats
            if f in norm_features and not np.isnan(norm_features[f][i])
        ]
        scores[domain] = float(np.mean(vals)) if vals else float("nan")
    return scores


def _coverage(rec: dict, profile: ClassProfile) -> tuple[int, int]:
    """Coverage relative to the token's CLASS spec — how many of *its* applicable
    features have data (so a monetary asset isn't dinged for missing P/F)."""
    feats = [f for feats in profile.feature_spec.values() for f, _ in feats]
    present = sum(1 for f in feats if rec.get(f) is not None)
    return present, len(feats)


def _ismissing(x) -> bool:
    return x is None or (isinstance(x, float) and np.isnan(x))


def _apply_core_penalty(
    domain_scores: dict[str, float], profile: ClassProfile, *, penalize: bool, floor: float
) -> list[str]:
    """Floor any of the class's *required* domains that have no data, instead of
    renormalizing them away. Returns the domains penalized (for an advisory).

    E.g. a DeFi app with no measurable fees/revenue/TVL scores its `fundamental`
    domain at the penalty floor (0.0) rather than getting a free pass.
    """
    if not penalize:
        return []
    penalized = []
    for domain in profile.required_domains:
        if domain in profile.weights and _ismissing(domain_scores.get(domain)):
            domain_scores[domain] = floor
            penalized.append(domain)
    return penalized


def _advisories(rec: dict, cfg: dict) -> list[str]:
    """Non-fatal notes surfaced alongside the score (don't affect the number)."""
    out: list[str] = []
    if rec.get("_class") == "stablecoin":
        out.append("stablecoin — scored for adoption/distribution, not price upside")
    # Treasury hurdle: a token paying a real yield below the risk-free 10Y is
    # structurally less attractive to institutional capital. No-yield tokens
    # aren't flagged — they're simply not competing on yield.
    hurdle = cfg["reference"]["treasury_10y_yield_pct"] / 100.0
    ry = rec.get("real_yield")
    if ry is not None and 0 < ry < hurdle:
        out.append(f"real yield {ry:.1%} below {hurdle:.1%} treasury hurdle")
    return out


def _load_reference_dist(classes) -> dict[str, dict[str, np.ndarray]]:
    """{class: {feature: reference array}} for the given classes (best-effort)."""
    try:
        from dyor.reference import reference_distributions
        return {c: reference_distributions(c) for c in classes if c}
    except Exception:
        return {}


def score_universe(
    records: list[dict],
    config: dict | None = None,
    *,
    peer_groups: bool = False,
    penalize_missing_core: bool | None = None,
    reference_anchored: bool | None = None,
    reference_dist: dict[str, dict[str, np.ndarray]] | None = None,
) -> list[ScoreResult]:
    """Score and rank a universe of token records. Returns highest-first.

    Each token is scored with the profile for its `_class` (asset-class-aware):
    a DeFi app is judged on fees/revenue, a monetary asset on scarcity/adoption,
    a memecoin on distribution/social — so "no revenue" only hurts those expected
    to have it. `peer_groups=True` normalizes within each `_group` (category).
    `penalize_missing_core` overrides the config default (None = use config) — a
    runtime toggle for whether a missing core domain floors the score.

    `reference_anchored` (None = config default) ranks each token's features
    against its class's *fixed* reference basket instead of the ad-hoc universe,
    so a token's score/tier is reproducible across the analyze subject, peer
    tables, and the screener. `reference_dist` injects the distributions (tests);
    None loads them from the cached baskets.
    """
    cfg = config if config is not None else load_config()
    method = cfg["scoring"]["normalization"]
    penalize = (cfg["scoring"].get("penalize_missing_core", True)
                if penalize_missing_core is None else penalize_missing_core)
    floor = cfg["scoring"].get("missing_core_penalty", 0.0)
    anchored = (cfg["scoring"].get("reference_anchored", False)
                if reference_anchored is None else reference_anchored)

    ref_dist = None
    if anchored:
        ref_dist = (reference_dist if reference_dist is not None
                    else _load_reference_dist({r.get("_class") for r in records}))

    groups = [r.get("_group") for r in records] if peer_groups else None
    norm_features = _normalized_features(records, method, groups, ref_dist=ref_dist)

    results: list[ScoreResult] = []
    for i, rec in enumerate(records):
        profile = class_profile(rec.get("_class"), cfg)
        domain_scores = _domain_scores(norm_features, i, profile)

        advisories = _advisories(rec, cfg)
        penalized = _apply_core_penalty(domain_scores, profile, penalize=penalize, floor=floor)
        if penalized:
            doms = ", ".join(DOMAIN_LABEL.get(d, d) for d in penalized)
            advisories.insert(0, f"{profile.label} with no {doms} data — {doms} domain penalized")

        results.append(
            score_token(
                rec.get("token", f"token_{i}"),
                domain_scores,
                record=rec,
                weights=Weights(profile.weights),
                config=cfg,
                coverage=_coverage(rec, profile),
                advisories=advisories,
            )
        )

    results.sort(
        key=lambda r: (np.isnan(r.final_score), -(r.final_score if not np.isnan(r.final_score) else 0))
    )
    return results
