"""Cassette-replayed integration test for the Ethplorer client (free `freekey`).

Validates the top-holders shape used for holder concentration.
"""

import jsonschema
import pytest

from dyor.ingestion.ethplorer import EthplorerClient
from tests.schemas import ETHPLORER_HOLDER

pytestmark = [pytest.mark.integration, pytest.mark.vcr]

AAVE = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"


def test_top_token_holders_shape(sample_config):
    with EthplorerClient(sample_config, use_cache=False) as client:
        holders = client.top_token_holders(AAVE, limit=10)
    assert isinstance(holders, list) and holders
    assert {"address", "balance", "share"} <= set(holders[0])
    assert holders[0]["share"] >= holders[-1]["share"]  # returned top-first
    jsonschema.validate(holders[0], ETHPLORER_HOLDER)  # contract test — catches drift
