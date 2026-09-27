"""Tests for the capability additions: robustness, screen, memo, portfolio."""

import math

from dyor.memo import memo_from_analysis
from dyor.pipeline import score_universe
from dyor.sample_data import SAMPLE_UNIVERSE
from dyor.screen import screen


# --- A. confidence / robustness -------------------------------------------

def test_tier_stability_and_confidence_present():
    for r in score_universe(SAMPLE_UNIVERSE):
        assert 0.0 <= r.tier_stability <= 1.0 or math.isnan(r.tier_stability)
        assert r.confidence in {"high", "medium", "low", "none"}


def test_gated_token_is_perfectly_stable():
    # deadcoin is zeroed by the gate → tier D regardless of weights → stability 1.0
    res = {r.token: r for r in score_universe(SAMPLE_UNIVERSE)}
    assert res["deadcoin"].tier_stability == 1.0


# --- C. screen ------------------------------------------------------------

def test_screen_min_tier_and_no_flags():
    rows = screen(SAMPLE_UNIVERSE, min_tier="B", no_flags=True)
    assert all(r["tier"][0] in ("A", "B") for r in rows)
    assert all(not r["flags"] for r in rows)
    # deadcoin (gated) and highfdv (flagged/D) excluded
    tokens = {r["token"] for r in rows}
    assert "deadcoin" not in tokens and "highfdv-lowfloat" not in tokens


def test_screen_feature_min():
    rows = screen(SAMPLE_UNIVERSE, feature_min={"value_accrual": 0.9})
    assert {r["token"] for r in rows} <= {"hyperliquid"}  # only the strong token sink


def test_screen_limit():
    assert len(screen(SAMPLE_UNIVERSE, limit=2)) == 2


# --- D. memo --------------------------------------------------------------

def test_memo_renders_sections():
    analysis = {
        "query": "x", "rank": 2, "peer_count": 5,
        "resolved": {"name": "Hyperliquid", "symbol": "HYPE"},
        # the serializer's 0–100 display scale (coverage / stability are percentages)
        "score": {"tier": "B — qualified", "final_score": 62.0, "scale": 100, "coverage": 80,
                  "tier_stability": 90, "confidence": "high", "flags": [],
                  "advisories": ["real yield 2% below 4.5% treasury hurdle"],
                  "domain_scores": {"fundamental": 40.0, "tokenomics": 80.0, "onchain": 70.0}},
        "record": {"class": {"label": "DeFi protocol", "description": "Cash-flow app."},
                   "features": {"address_growth": 0.18, "unlock_overhang": 0.77,
                                "fdv_mcap_ratio": 1.4, "value_accrual": 0.95},
                   "market": {"ath_change_pct": -20.0}, "feeds": {}},
    }
    memo = memo_from_analysis(analysis)
    assert "Hyperliquid (HYPE)" in memo
    assert "score 62.0/100" in memo and "coverage 80%" in memo and "**tokenomics** (80/100)" in memo
    assert "Thin data" not in memo                # 80% coverage is not thin
    assert "## Risks" in memo and "## Break your thesis" in memo
    assert "Unlock overhang" in memo            # 77% overhang surfaced
    assert "not financial advice" in memo.lower()


def test_memo_unresolved():
    assert "Could not resolve" in memo_from_analysis({"query": "zzz", "resolved": None})
