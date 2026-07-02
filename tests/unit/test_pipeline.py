"""End-to-end golden test: the sample universe must produce sensible calls.

This is the regression guard for the whole normalize→weight→gate chain. If a
refactor silently breaks gating or normalization, these assertions catch it.
"""

import math

import numpy as np
import pytest

from dyor.pipeline import score_universe
from dyor.sample_data import SAMPLE_UNIVERSE


def _by_token(results):
    return {r.token: r for r in results}


def test_universe_scores_in_bounds():
    results = score_universe(SAMPLE_UNIVERSE)
    for r in results:
        assert math.isnan(r.final_score) or 0.0 <= r.final_score <= 1.0


def test_dead_token_is_zeroed():
    res = _by_token(score_universe(SAMPLE_UNIVERSE))["deadcoin"]
    assert res.final_score == 0.0
    assert "dead_token" in res.flags or "unverified_contract" in res.flags


def test_high_fdv_low_float_is_capped():
    res = _by_token(score_universe(SAMPLE_UNIVERSE))["highfdv-lowfloat"]
    assert "extreme_fdv_mcap" in res.flags
    assert res.final_score <= 0.40


def test_ranking_is_descending():
    results = score_universe(SAMPLE_UNIVERSE)
    finals = [r.final_score for r in results if not math.isnan(r.final_score)]
    assert finals == sorted(finals, reverse=True)


def test_winner_is_a_clean_token():
    results = score_universe(SAMPLE_UNIVERSE)
    assert results[0].token not in {"deadcoin", "highfdv-lowfloat"}


def test_coverage_is_computed():
    results = score_universe(SAMPLE_UNIVERSE)
    for r in results:
        assert r.features_total > 0
        assert 0.0 <= r.coverage <= 1.0
        assert r.features_present <= r.features_total


def test_treasury_advisory_fires_below_hurdle():
    # a token paying 2% real yield (below the ~4.5% hurdle) gets an advisory
    rec = {"token": "x", "real_yield": 0.02, "price_to_fees": 10.0}
    res = score_universe([rec])[0]
    assert any("hurdle" in a for a in res.advisories)


def test_treasury_advisory_silent_without_yield():
    rec = {"token": "y", "real_yield": 0.0, "price_to_fees": 10.0}
    res = score_universe([rec])[0]
    assert res.advisories == []  # no yield → not competing on yield → no flag


def test_peer_groups_normalize_within_category():
    # Two categories. In "dex", A is the cheaper (better) P/F; in "lend", C is.
    records = [
        {"token": "A", "price_to_fees": 5.0, "_group": "dex"},
        {"token": "B", "price_to_fees": 50.0, "_group": "dex"},
        {"token": "C", "price_to_fees": 8.0, "_group": "lend"},
        {"token": "D", "price_to_fees": 80.0, "_group": "lend"},
    ]
    res = {r.token: r for r in score_universe(records, peer_groups=True)}
    # Within its own group, each cheap token should out-score its pricey peer.
    assert res["A"].domain_scores["fundamental"] > res["B"].domain_scores["fundamental"]
    assert res["C"].domain_scores["fundamental"] > res["D"].domain_scores["fundamental"]
    # A (P/F 5) and C (P/F 8) are each top of their group → similar normalized score,
    # even though globally C would rank below A.
    assert res["A"].domain_scores["fundamental"] == res["C"].domain_scores["fundamental"]


# --- reference-anchored scoring (the fix for cross-context tier flutter) ----

_REF = {"defi": {
    "price_to_fees": np.array([5.0, 10.0, 20.0, 40.0, 80.0]),
    "mc_tvl": np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
}}
_SUBJECT = {"token": "rpl", "_class": "defi", "price_to_fees": 15.0, "mc_tvl": 2.5}
# Two genuinely different peer sets — weak peers vs strong peers.
_WEAK = [_SUBJECT, {"token": "p", "_class": "defi", "price_to_fees": 200.0, "mc_tvl": 0.1}]
_STRONG = [_SUBJECT,
           {"token": "q1", "_class": "defi", "price_to_fees": 3.0, "mc_tvl": 9.0},
           {"token": "q2", "_class": "defi", "price_to_fees": 4.0, "mc_tvl": 8.0}]


def test_reference_anchored_score_is_universe_independent():
    """Same token + same reference basket → identical score/tier regardless of
    what else is in the batch. This is what stops a token fluttering A/B between
    the analyze subject, a peer table, and the screener."""
    a = {r.token: r for r in score_universe(_WEAK, reference_anchored=True, reference_dist=_REF)}["rpl"]
    b = {r.token: r for r in score_universe(_STRONG, reference_anchored=True, reference_dist=_REF)}["rpl"]
    assert a.tier == b.tier
    assert a.final_score == pytest.approx(b.final_score)
    assert a.domain_scores["fundamental"] == pytest.approx(b.domain_scores["fundamental"])


def test_relative_score_is_universe_dependent():
    """Control: with relative normalization the SAME token scores differently
    across the two peer sets — the bug the reference anchor fixes."""
    a = {r.token: r for r in score_universe(_WEAK, reference_anchored=False)}["rpl"]
    b = {r.token: r for r in score_universe(_STRONG, reference_anchored=False)}["rpl"]
    assert a.domain_scores["fundamental"] != pytest.approx(b.domain_scores["fundamental"])
