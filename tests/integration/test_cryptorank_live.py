"""Cassette-replayed integration test for the CryptoRank v0 client (open, no key).

The cassette preserves the `v0/coins/{key}` shape the parser was written against.
NOTE: v0 went behind a Cloudflare challenge in Sep 2026, so this cassette can no
longer be re-recorded; it stays as the contract the v0 path is held to. The test
pins the keyless path so a developer's DYOR_CRYPTORANK_API_KEY (which routes the
client to v3) does not change which requests are made.
"""

import jsonschema
import pytest

from dyor.config import Settings
from dyor.ingestion import cryptorank as cr_mod
from dyor.ingestion.cryptorank import CryptoRankClient
from tests.schemas import CRYPTORANK_COIN

pytestmark = [pytest.mark.integration, pytest.mark.vcr]


def test_coin_carries_supply_and_vesting_flag(sample_config, monkeypatch):
    monkeypatch.setattr(cr_mod, "get_settings", lambda: Settings(_env_file=None))
    with CryptoRankClient(sample_config, use_cache=False) as client:
        coin = client.coin("aave")
    # the fields unlock_overhang depends on must be present
    assert "hasVesting" in coin
    assert "availableSupply" in coin
    assert "maxSupply" in coin
    jsonschema.validate(coin, CRYPTORANK_COIN)  # contract test — catches drift
