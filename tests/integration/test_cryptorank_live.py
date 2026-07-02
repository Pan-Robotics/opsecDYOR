"""Cassette-replayed integration test for the CryptoRank v0 client (open, no key).

Validates the open `v0/coins/{key}` shape we depend on for unlock overhang.
"""

import jsonschema
import pytest

from dyor.ingestion.cryptorank import CryptoRankClient
from tests.schemas import CRYPTORANK_COIN

pytestmark = [pytest.mark.integration, pytest.mark.vcr]


def test_coin_carries_supply_and_vesting_flag(sample_config):
    with CryptoRankClient(sample_config, use_cache=False) as client:
        coin = client.coin("aave")
    # the fields unlock_overhang depends on must be present
    assert "hasVesting" in coin
    assert "availableSupply" in coin
    assert "maxSupply" in coin
    jsonschema.validate(coin, CRYPTORANK_COIN)  # contract test — catches drift
