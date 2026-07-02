"""Illustrative sample universe for demos, the dashboard, and a smoke test.

These numbers are HAND-CRAFTED for illustration, not live data — they encode the
kinds of calls the framework should make: a revenue play that scores well, a
sound monetary anchor, a privacy play, a high-FDV/low-float unlock overhang that
gets capped, and a dead token that gets zeroed. Replace with live ingestion
output (identity → metrics) for real scoring.
"""

from __future__ import annotations

SAMPLE_UNIVERSE: list[dict] = [
    {
        "token": "hyperliquid",
        "price_to_fees": 12.4, "price_to_sales": 16.0, "mc_tvl": 2.0, "real_yield": 0.07,
        "fdv_mcap_ratio": 1.4, "unlock_pct_of_volume": 0.35, "float_ratio": 0.33,
        "inflation_rate": 0.05, "value_accrual": 0.95,  # strong hard-coded buyback
        "unlock_overhang": 0.77,  # low float — large vesting overhang ahead
        "top10_concentration": 0.24, "address_growth": 0.18, "reserve_trend": -0.30,
        "social_trend": 0.40, "social_sentiment": 0.92, "dev_commit_trend": 0.55,
        "contract_verified": True, "team_anonymous": False, "audited": True,
        "days_since_last_commit": 2, "drawdown_from_ath_pct": 12.0, "daily_volume_usd": 8.0e8,
    },
    {
        "token": "bitcoin",
        "price_to_fees": 60.0, "price_to_sales": 70.0, "mc_tvl": None, "real_yield": 0.0,
        "fdv_mcap_ratio": 1.05, "unlock_pct_of_volume": 0.02, "float_ratio": 0.95,
        "inflation_rate": 0.018, "value_accrual": 0.0,  # no protocol token sink
        "unlock_overhang": 0.0,  # no vesting schedule
        "top10_concentration": 0.10, "address_growth": 0.06, "reserve_trend": -0.55,
        "social_trend": 0.20, "social_sentiment": 0.95, "dev_commit_trend": 0.35,
        "contract_verified": True, "team_anonymous": False, "audited": True,
        "days_since_last_commit": 1, "drawdown_from_ath_pct": 38.0, "daily_volume_usd": 2.0e10,
    },
    {
        "token": "zcash",
        "price_to_fees": 90.0, "price_to_sales": 110.0, "mc_tvl": None, "real_yield": 0.0,
        "fdv_mcap_ratio": 1.20, "unlock_pct_of_volume": 0.05, "float_ratio": 0.83,
        "inflation_rate": 0.02, "value_accrual": 0.0, "unlock_overhang": 0.06,
        "top10_concentration": 0.18, "address_growth": 0.22, "reserve_trend": -0.20,
        "social_trend": 0.60, "social_sentiment": 0.80, "dev_commit_trend": 0.45,
        "contract_verified": True, "team_anonymous": False, "audited": True,
        "days_since_last_commit": 5, "drawdown_from_ath_pct": 19.0, "daily_volume_usd": 4.0e8,
    },
    {
        "token": "highfdv-lowfloat",  # classic dilution overhang → gate caps it
        "price_to_fees": 40.0, "price_to_sales": 55.0, "mc_tvl": 8.0, "real_yield": 0.01,
        "fdv_mcap_ratio": 14.0, "unlock_pct_of_volume": 2.5, "float_ratio": 0.07,
        "inflation_rate": 0.40, "value_accrual": 0.10, "unlock_overhang": 0.90,
        "top10_concentration": 0.62, "address_growth": -0.05, "reserve_trend": 0.10,
        "social_trend": 0.30, "social_sentiment": 0.55, "dev_commit_trend": 0.20,
        "contract_verified": True, "team_anonymous": False, "audited": True,
        "days_since_last_commit": 20, "drawdown_from_ath_pct": 55.0, "daily_volume_usd": 1.0e7,
    },
    {
        "token": "deadcoin",  # no commits 6+mo + ~total drawdown → gate zeroes it
        "price_to_fees": None, "price_to_sales": None, "mc_tvl": 200.0, "real_yield": 0.0,
        "fdv_mcap_ratio": 9.0, "unlock_pct_of_volume": 0.0, "float_ratio": 0.50,
        "inflation_rate": 0.0, "value_accrual": 0.0, "unlock_overhang": 0.45,
        "top10_concentration": 0.80, "address_growth": -0.40, "reserve_trend": 0.30,
        "social_trend": -0.50, "social_sentiment": 0.30, "dev_commit_trend": -0.60,
        "contract_verified": False, "team_anonymous": True, "audited": False,
        "days_since_last_commit": 400, "drawdown_from_ath_pct": 99.6, "daily_volume_usd": 120.0,
    },
]
