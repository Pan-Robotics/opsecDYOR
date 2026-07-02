import pytest

from dyor.metrics import onchain, tokenomics, valuation


# -- valuation --------------------------------------------------------------

def test_price_to_fees_worked_example():
    # $1B mcap / $100M fees → P/F of 10 (the doc's worked example)
    assert valuation.price_to_fees(1_000_000_000, 100_000_000) == pytest.approx(10.0)


def test_safe_div_guards_zero_and_none():
    assert valuation.price_to_fees(1_000, 0) is None
    assert valuation.price_to_sales(None, 100) is None
    assert valuation.mc_tvl(100, -5) is None  # non-positive denominator


def test_fdv_and_mcap_and_ratio():
    assert valuation.fdv(2.0, 1_000) == 2_000
    assert valuation.market_cap(2.0, 400) == 800
    assert valuation.fdv_mcap_ratio(1_000, 250) == pytest.approx(4.0)


def test_outstanding_fdv_excludes_treasury():
    assert valuation.outstanding_fdv(2.0, 1_000, unallocated_treasury=200) == 1_600


def test_real_yield_fraction():
    assert valuation.real_yield(5_000_000, 100_000_000) == pytest.approx(0.05)


# -- tokenomics -------------------------------------------------------------

def test_unlock_pct_of_volume_absorption():
    # unlock worth 1.5 days of volume = high sell-pressure risk
    assert tokenomics.unlock_pct_of_volume(15_000, 10_000) == pytest.approx(1.5)


def test_float_ratio_and_inflation():
    assert tokenomics.float_ratio(250, 1_000) == pytest.approx(0.25)
    assert tokenomics.inflation_rate(20, 1_000) == pytest.approx(0.02)


def test_insider_share_handles_zero_total():
    assert tokenomics.insider_share(10, 0) is None


def test_value_accrual_fraction_and_clamp():
    # 30% of revenue reaches holders → 0.30 token-sink strength
    assert tokenomics.value_accrual(3, 10) == pytest.approx(0.30)
    # reported holders rev can exceed booked revenue → clamp at 1.0
    assert tokenomics.value_accrual(15, 10) == 1.0
    # no revenue → undefined
    assert tokenomics.value_accrual(5, 0) is None


def test_unlock_overhang_counts_only_when_vesting():
    # 22% circulating of 100 max, vesting → 78% locked overhang
    assert tokenomics.unlock_overhang(22, 100, True) == pytest.approx(0.78)
    # not vesting → no overhang even if supply not all circulating (e.g. unmined)
    assert tokenomics.unlock_overhang(22, 100, False) == 0.0
    # missing supply → undefined
    assert tokenomics.unlock_overhang(None, 100, True) is None
    assert tokenomics.unlock_overhang(50, 0, True) is None


# -- onchain ----------------------------------------------------------------

def test_top_n_concentration():
    balances = [50, 30, 10, 5, 5]
    # top-2 of 100 total = 0.80
    assert onchain.top_n_concentration(balances, n=2) == pytest.approx(0.80)


def test_gini_equal_is_zero():
    assert onchain.gini([10, 10, 10, 10]) == pytest.approx(0.0)


def test_gini_concentrated_is_high():
    g = onchain.gini([100, 0, 0, 0])
    assert g > 0.6


def test_nakamoto_coefficient():
    # one holder already exceeds 51%
    assert onchain.nakamoto_coefficient([60, 20, 20]) == 1
    # need two to clear 51%
    assert onchain.nakamoto_coefficient([40, 40, 20]) == 2


def test_trend_slope_sign():
    assert onchain.trend_slope([1, 2, 3, 4]) > 0
    assert onchain.trend_slope([4, 3, 2, 1]) < 0
    assert onchain.trend_slope([5]) is None  # too few points


def test_series_growth_relative_change():
    # first third ≈ 100, last third ≈ 200 → +100% growth
    series = [100, 100, 100, 150, 150, 150, 200, 200, 200]
    assert onchain.series_growth(series) == pytest.approx(1.0)


def test_series_growth_negative_and_guards():
    # declining series → negative growth
    assert onchain.series_growth([200, 200, 100, 100, 50, 50]) < 0
    assert onchain.series_growth([1, 2]) is None              # too few points
    assert onchain.series_growth([0, 0, 0, 5, 5, 5]) is None  # zero baseline
