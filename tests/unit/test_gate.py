import pytest

from dyor.scoring import gate


@pytest.fixture
def cfg(sample_config):
    return sample_config


def test_clean_token_passes(cfg):
    rec = {
        "contract_verified": True, "team_anonymous": False, "audited": True,
        "fdv_mcap_ratio": 1.3, "days_since_last_commit": 3,
        "drawdown_from_ath_pct": 20.0, "daily_volume_usd": 5.0e8,
    }
    result = gate.evaluate(rec, cfg)
    assert result.flags == []
    assert result.cap is None
    assert result.apply(0.9) == 0.9


def test_unverified_contract_zeroes(cfg):
    result = gate.evaluate({"contract_verified": False}, cfg)
    assert "unverified_contract" in result.flags
    assert result.zeroed
    assert result.apply(0.95) == 0.0


def test_extreme_fdv_mcap_caps(cfg):
    result = gate.evaluate({"fdv_mcap_ratio": 14.0}, cfg)
    assert "extreme_fdv_mcap" in result.flags
    assert result.apply(0.9) == pytest.approx(0.40)


def test_dead_token_any_one_criterion(cfg):
    # stale repo alone trips it
    assert "dead_token" in gate.evaluate({"days_since_last_commit": 400}, cfg).flags
    # near-zero volume alone trips it
    assert "dead_token" in gate.evaluate({"daily_volume_usd": 50.0}, cfg).flags
    # price drawdown alone must NOT trip it (price action, not project death)
    assert "dead_token" not in gate.evaluate({"drawdown_from_ath_pct": 99.7}, cfg).flags


def test_strictest_cap_wins(cfg):
    # anonymous (cap 0.40) + unverified (zero) → strictest (0.0) wins
    rec = {"team_anonymous": True, "contract_verified": False}
    result = gate.evaluate(rec, cfg)
    assert result.apply(1.0) == 0.0


def test_missing_data_does_not_trip(cfg):
    # absent fields should not raise or flag
    result = gate.evaluate({}, cfg)
    assert result.flags == []
    assert result.cap is None
