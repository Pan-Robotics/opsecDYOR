"""Cassette-replayed integration test for the full ingest-to-score path. OPT-IN.

Records the live CoinGecko + DefiLlama calls for a 2-token universe, then proves
records build and score offline. See test_defillama_live.py for the workflow.
"""

import math

import pytest

from dyor.collect import Collector, Target
from dyor.pipeline import score_universe

pytestmark = [pytest.mark.integration, pytest.mark.vcr]

TARGETS = [
    Target("aave", "aave", "aave-dao", "aave", "aave",
           "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"),
    Target("uniswap", "uniswap", "Uniswap", "uniswap", "uniswap",
           "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"),
]


def test_collect_builds_scorable_records(sample_config):
    with Collector(sample_config, use_cache=False) as collector:
        records = collector.collect(TARGETS)

    assert {r["token"] for r in records} == {"aave", "uniswap"}
    # live fundamentals should be populated for these fee-generating protocols
    aave = next(r for r in records if r["token"] == "aave")
    assert aave["price_to_fees"] is not None and aave["price_to_fees"] > 0
    assert aave["daily_volume_usd"] is not None
    # token-sink + dev signals come from the new feeds. value_accrual depends on
    # DefiLlama holders-revenue coverage (varies by snapshot) — assert presence.
    assert "value_accrual" in aave
    assert aave["days_since_last_commit"] is not None and aave["days_since_last_commit"] >= 0
    # Santiment on-chain + dev-activity growth signals
    assert aave["address_growth"] is not None
    assert aave["dev_commit_trend"] is not None
    # CryptoRank unlock overhang + Ethplorer holder concentration
    assert aave["unlock_overhang"] is not None
    assert aave["top10_concentration"] is not None and 0 <= aave["top10_concentration"] <= 1

    results = score_universe(records, sample_config)
    assert len(results) == 2
    for r in results:
        assert math.isnan(r.final_score) or 0.0 <= r.final_score <= 1.0
