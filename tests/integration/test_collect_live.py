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


def test_collect_builds_scorable_records(sample_config, monkeypatch):
    # The Santiment identity list is ~400 KB and only feeds the slug map (unit-
    # tested on fixtures); keep it out of the cassette.
    monkeypatch.setattr("dyor.ingestion.santiment.SantimentClient.all_projects", lambda self: [])
    from dyor.config import get_settings
    has_gh_token = bool(get_settings().github_token)

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
    # GitHub is token-gated (60 req/HOUR anonymous): off without DYOR_GITHUB_TOKEN.
    if has_gh_token:
        assert aave["days_since_last_commit"] is not None and aave["days_since_last_commit"] >= 0
    else:
        assert aave["_feeds"]["github"] == "off" and aave["days_since_last_commit"] is None
    # CoinGecko meta now carries the watchlist count + audit status from DefiLlama
    assert aave["watchlist_users"] is not None and aave["watchlist_users"] > 0
    assert "audited" in aave
    # Santiment on-chain + dev-activity growth signals
    assert aave["address_growth"] is not None
    assert aave["dev_commit_trend"] is not None
    # CryptoRank: the open v0 endpoint is dead and the v3 free plan has no vesting
    # endpoints, so the feed is `off` (never `error`) and the feature is n/a.
    assert aave["_feeds"]["cryptorank"] == "off" and aave["unlock_overhang"] is None
    # Ethplorer holder concentration + Sourcify verification (Ethereum deployment)
    assert aave["top10_concentration"] is not None and 0 <= aave["top10_concentration"] <= 1
    assert aave["contract_verified"] is True

    results = score_universe(records, sample_config)
    assert len(results) == 2
    for r in results:
        assert math.isnan(r.final_score) or 0.0 <= r.final_score <= 1.0
