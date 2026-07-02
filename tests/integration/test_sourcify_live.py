"""Cassette-replayed integration test for the Sourcify client (open, no key)."""

import pytest

from dyor.ingestion.sourcify import SourcifyClient

pytestmark = [pytest.mark.integration, pytest.mark.vcr]

AAVE = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"
NOT_A_CONTRACT = "0x0000000000000000000000000000000000000001"


def test_verified_contract_returns_true(sample_config):
    with SourcifyClient(sample_config, use_cache=False) as client:
        assert client.is_verified(AAVE) is True


def test_unknown_address_returns_none_not_false(sample_config):
    # absence from Sourcify must be None (unknown), never False (which would gate)
    with SourcifyClient(sample_config, use_cache=False) as client:
        assert client.is_verified(NOT_A_CONTRACT) is None
