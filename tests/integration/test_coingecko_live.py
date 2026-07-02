"""Cassette-replayed integration tests for the CoinGecko client. OPT-IN.

See tests/integration/test_defillama_live.py for the record/replay workflow.

These hit small, representative endpoints (asset_platforms + a 2-coin markets
call) to keep cassettes tiny. The heavy `/coins/list?include_platform=true`
endpoint (~18k coins, 10MB+) is deliberately NOT recorded here — its explode/
join logic is covered by fixture-based unit tests in tests/unit/test_identity.py.
Record it ad hoc if you need to validate its live shape.
"""

import jsonschema
import pytest

from dyor.ingestion.coingecko import CoinGeckoClient
from tests.schemas import COINGECKO_MARKET

pytestmark = [pytest.mark.integration, pytest.mark.vcr]


def test_asset_platforms_map(sample_config):
    with CoinGeckoClient(sample_config, use_cache=False) as client:
        platforms = client.asset_platforms()
    assert isinstance(platforms, list) and platforms
    assert any(p.get("id") == "ethereum" for p in platforms)


def test_coin_sentiment(sample_config):
    with CoinGeckoClient(sample_config, use_cache=False) as client:
        pct = client.coin_sentiment("aave")
    assert pct is None or 0.0 <= pct <= 100.0  # up-vote percentage


def test_search_resolves_name(sample_config):
    with CoinGeckoClient(sample_config, use_cache=False) as client:
        coins = client.search("aave").get("coins", [])
    assert any(c["id"] == "aave" for c in coins)
    assert {"id", "symbol", "name"} <= set(coins[0])


def test_coin_by_contract_is_cross_chain(sample_config):
    aave_eth = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"
    with CoinGeckoClient(sample_config, use_cache=False) as client:
        detail = client.coin_by_contract("ethereum", aave_eth)
    assert detail["id"] == "aave"
    # the unified token lists every chain it's deployed on
    assert len(detail.get("platforms") or {}) > 1
    assert "ethereum" in detail["platforms"]


def test_markets_shape(sample_config):
    with CoinGeckoClient(sample_config, use_cache=False) as client:
        rows = client.markets(["bitcoin", "ethereum"])
    assert {r["id"] for r in rows} == {"bitcoin", "ethereum"}
    # the fields the metrics layer depends on must be present
    sample = rows[0]
    for field in ("market_cap", "fully_diluted_valuation",
                  "circulating_supply", "total_supply"):
        assert field in sample
    jsonschema.validate(sample, COINGECKO_MARKET)  # contract test — catches drift
