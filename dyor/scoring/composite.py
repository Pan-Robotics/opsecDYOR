"""Composite scoring: combine normalized per-domain scores → gate → risk tier.

Input is per-token, per-domain normalized scores already in [0, 1] (produced by
`normalize` over a peer set). This module only does the weighted combination,
gating, and tier mapping — it is deliberately ignorant of how the domain scores
were computed so it stays trivially testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from dyor.config import load_config
from dyor.scoring.gate import GateResult, evaluate
from dyor.scoring.weights import Weights, load_weights


@dataclass(frozen=True)
class ScoreResult:
    token: str
    raw_score: float          # weighted sum before gating, [0, 1]
    final_score: float        # after gating, [0, 1]
    tier: str
    flags: list[str]
    domain_scores: dict[str, float]
    coverage: float = 1.0     # fraction of scored features with data, [0, 1]
    features_present: int = 0
    features_total: int = 0
    advisories: list[str] = field(default_factory=list)  # non-fatal notes
    tier_stability: float = 1.0  # fraction of ±20% weight perturbations keeping the tier

    @property
    def confidence(self) -> str:
        """Coarse confidence label from data coverage + tier robustness."""
        if math.isnan(self.coverage):
            return "none"
        score = 0.6 * self.coverage + 0.4 * (self.tier_stability if not math.isnan(self.tier_stability) else 0)
        return "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"


def _is_missing(x: float | None) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def combine(domain_scores: dict[str, float], weights: Weights) -> float:
    """Weighted sum over the domains that have a (non-missing) score.

    Weights are renormalized across only the present domains so a token missing
    one feed isn't unfairly dragged toward zero. Returns NaN if nothing scored.
    """
    present = {
        d: s for d, s in domain_scores.items()
        if d in weights.by_domain and not _is_missing(s)
    }
    if not present:
        return float("nan")
    total_w = sum(weights.get(d) for d in present)
    if total_w == 0:
        return float("nan")
    return sum(weights.get(d) * present[d] for d in present) / total_w


def _tier_stability(domain_scores: dict, weights: Weights, gate_result: GateResult,
                    cfg: dict, base_final: float) -> float:
    """Robustness: fraction of ±20% per-domain weight perturbations that keep the
    tier. A token whose tier flips under a small re-weighting is a fragile call."""
    if _is_missing(base_final):
        return float("nan")
    base_letter = to_tier(base_final, cfg).strip()[:1]
    perts: list[dict] = []
    for d in weights.by_domain:
        for mult in (0.8, 1.2):
            w = dict(weights.by_domain)
            w[d] *= mult
            perts.append(w)
    if not perts:
        return 1.0
    same = 0
    for wd in perts:
        total = sum(wd.values()) or 1.0
        f = gate_result.apply(combine(domain_scores, Weights({k: v / total for k, v in wd.items()})))
        if not _is_missing(f) and to_tier(f, cfg).strip()[:1] == base_letter:
            same += 1
    return same / len(perts)


def to_tier(score: float, config: dict | None = None) -> str:
    cfg = config if config is not None else load_config()
    tiers = cfg["scoring"]["tiers"]  # assumed sorted high→low by `min`
    if _is_missing(score):
        return "N/A — insufficient data"
    for tier in tiers:
        if score >= tier["min"]:
            return tier["label"]
    return tiers[-1]["label"]


def score_token(
    token: str,
    domain_scores: dict[str, float],
    record: dict | None = None,
    *,
    weights: Weights | None = None,
    config: dict | None = None,
    gate_result: GateResult | None = None,
    coverage: tuple[int, int] = (0, 0),
    advisories: list[str] | None = None,
) -> ScoreResult:
    """End-to-end for one token: combine → gate → tier.

    `record` carries the raw flags the gate inspects (contract_verified,
    fdv_mcap_ratio, days_since_last_commit, ...). Pass a precomputed
    `gate_result` to skip re-evaluation. `coverage` is (features_present,
    features_total) for the data-completeness indicator.
    """
    cfg = config if config is not None else load_config()
    w = weights if weights is not None else load_weights(cfg)

    raw = combine(domain_scores, w)

    if gate_result is None:
        gate_result = evaluate(record or {}, cfg)
    final = gate_result.apply(raw) if not _is_missing(raw) else raw

    present, total = coverage
    return ScoreResult(
        token=token,
        raw_score=raw,
        final_score=final,
        tier=to_tier(final, cfg),
        flags=gate_result.flags,
        domain_scores=dict(domain_scores),
        coverage=(present / total) if total else float("nan"),
        features_present=present,
        features_total=total,
        advisories=list(advisories or []),
        tier_stability=_tier_stability(domain_scores, w, gate_result, cfg, final),
    )
