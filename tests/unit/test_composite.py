import math

import pytest

from dyor.scoring import composite
from dyor.scoring.gate import GateResult
from dyor.scoring.weights import Weights


@pytest.fixture
def weights():
    return Weights({"fundamental": 0.5, "tokenomics": 0.3, "onchain": 0.2})


def test_combine_weighted_sum(weights):
    scores = {"fundamental": 1.0, "tokenomics": 0.0, "onchain": 0.5}
    # 0.5*1 + 0.3*0 + 0.2*0.5 = 0.6
    assert composite.combine(scores, weights) == pytest.approx(0.6)


def test_combine_renormalizes_over_present_domains(weights):
    # only fundamental present → result equals that domain's score
    assert composite.combine({"fundamental": 0.8}, weights) == pytest.approx(0.8)


def test_combine_all_missing_is_nan(weights):
    assert math.isnan(composite.combine({"fundamental": None}, weights))


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        Weights({"a": 0.5, "b": 0.2})


def test_to_tier_thresholds(sample_config):
    assert "A" in composite.to_tier(0.85, sample_config)
    assert "D" in composite.to_tier(0.10, sample_config)
    assert "insufficient" in composite.to_tier(float("nan"), sample_config)


def test_score_token_applies_gate(sample_config):
    domain_scores = {"fundamental": 0.9, "tokenomics": 0.9, "onchain": 0.9,
                     "social": 0.9, "dev": 0.9}
    # an unverified contract must zero an otherwise-excellent score
    rec = {"contract_verified": False}
    result = composite.score_token("x", domain_scores, rec, config=sample_config)
    assert result.raw_score > 0.8
    assert result.final_score == 0.0
    assert "unverified_contract" in result.flags


def test_score_token_precomputed_gate(sample_config):
    res = composite.score_token(
        "y", {"fundamental": 0.6}, gate_result=GateResult(flags=["no_audit"], cap=0.5),
        config=sample_config,
    )
    assert res.final_score == pytest.approx(0.5)
