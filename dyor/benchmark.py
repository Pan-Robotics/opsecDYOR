"""Benchmark harness — does the scorer reproduce known good/bad calls?

The framework's "benchmark to advance" gate: a small labeled set of cases with
expected outcomes (tier, gate flags, zeroed, score band). Run the scorer over
the whole set (so normalization has peers) and check each expectation. Re-run
after any weight/gating change to confirm known calls still hold.

`run_benchmark` is pure (cases in → report out), so it doubles as a regression
test and a CLI command (`dyor benchmark`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from dyor.pipeline import score_universe


@dataclass(frozen=True)
class Case:
    """One labeled expectation over a token record."""

    name: str
    record: dict
    expect_tier: str | None = None        # leading tier letter, e.g. "A"
    expect_flags: list[str] = field(default_factory=list)  # must all be present
    expect_zeroed: bool | None = None     # final score must be exactly 0.0
    min_final: float | None = None
    max_final: float | None = None


@dataclass
class CaseResult:
    name: str
    passed: bool
    final_score: float
    tier: str
    flags: list[str]
    reasons: list[str]                     # why it failed (empty if passed)


@dataclass
class BenchmarkReport:
    results: list[CaseResult]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else float("nan")

    @property
    def ok(self) -> bool:
        return self.passed == self.total


def _check(case: Case, score) -> CaseResult:
    reasons: list[str] = []
    final = score.final_score

    if case.expect_tier is not None and not score.tier.startswith(case.expect_tier):
        reasons.append(f"tier {score.tier!r} != expected {case.expect_tier!r}")
    for flag in case.expect_flags:
        if flag not in score.flags:
            reasons.append(f"missing flag {flag!r}")
    if case.expect_zeroed is not None:
        is_zero = final == 0.0
        if is_zero != case.expect_zeroed:
            reasons.append(f"zeroed={is_zero}, expected {case.expect_zeroed}")
    if case.min_final is not None and not (math.isnan(final)) and final < case.min_final:
        reasons.append(f"final {final:.3f} < min {case.min_final}")
    if case.max_final is not None and not (math.isnan(final)) and final > case.max_final:
        reasons.append(f"final {final:.3f} > max {case.max_final}")

    return CaseResult(case.name, not reasons, final, score.tier, list(score.flags), reasons)


def run_benchmark(cases: list[Case], config: dict | None = None) -> BenchmarkReport:
    """Score all case records together, then check each case's expectations."""
    records = [{**c.record, "token": c.name} for c in cases]
    results = {r.token: r for r in score_universe(records, config)}
    return BenchmarkReport([_check(c, results[c.name]) for c in cases])


# Default benchmark set — encodes the framework's signature calls. These hold
# given the peer set below; adjust together if you change the records.
DEFAULT_CASES: list[Case] = [
    Case(
        "strong-revenue-play",
        {"price_to_fees": 8, "price_to_sales": 10, "mc_tvl": 1.5, "real_yield": 0.08,
         "fdv_mcap_ratio": 1.1, "unlock_overhang": 0.05, "float_ratio": 0.9,
         "value_accrual": 0.9, "top10_concentration": 0.15, "address_growth": 0.3,
         "dev_commit_trend": 0.5, "social_sentiment": 0.9,
         "contract_verified": True, "days_since_last_commit": 2,
         "drawdown_from_ath_pct": 15, "daily_volume_usd": 9e8},
        # NB: tier A (>0.8) needs a real universe's percentile spread; in a tiny
        # benchmark set the call we assert is "qualified (B+) and ungated".
        expect_zeroed=False, expect_flags=[], min_final=0.6,
    ),
    Case(
        "dilution-overhang",
        {"price_to_fees": 40, "price_to_sales": 60, "mc_tvl": 8, "real_yield": 0.0,
         "fdv_mcap_ratio": 14.0, "unlock_overhang": 0.85, "float_ratio": 0.07,
         "value_accrual": 0.1, "top10_concentration": 0.6, "address_growth": -0.1,
         "dev_commit_trend": 0.1, "daily_volume_usd": 1e7, "drawdown_from_ath_pct": 60},
        expect_flags=["extreme_fdv_mcap"], expect_tier="D",
    ),
    Case(
        "dead-token",
        {"price_to_fees": None, "mc_tvl": 200, "fdv_mcap_ratio": 9, "float_ratio": 0.5,
         "top10_concentration": 0.85, "address_growth": -0.5, "dev_commit_trend": -0.7,
         "contract_verified": False, "days_since_last_commit": 400,
         "drawdown_from_ath_pct": 99.6, "daily_volume_usd": 100},
        expect_zeroed=True, expect_flags=["dead_token"],
    ),
    Case(
        "sound-anchor",
        {"price_to_fees": 55, "price_to_sales": 65, "real_yield": 0.0,
         "fdv_mcap_ratio": 1.05, "unlock_overhang": 0.0, "float_ratio": 0.95,
         "top10_concentration": 0.1, "address_growth": 0.05, "dev_commit_trend": 0.3,
         "social_sentiment": 0.95, "contract_verified": True,
         "days_since_last_commit": 1, "drawdown_from_ath_pct": 38, "daily_volume_usd": 2e10},
        expect_zeroed=False,
    ),
]
