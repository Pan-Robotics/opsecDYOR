"""Cassette-replayed integration tests for the DefiLlama client.

OPT-IN: excluded from the default `pytest` run (see pyproject `addopts`). Run:

    # record once against live APIs (creates tests/cassettes/*.yaml):
    pytest -m integration --record-mode=once tests/integration/test_defillama_live.py

    # then replay offline forever (CI default — fails on any unseen request):
    pytest -m integration tests/integration/test_defillama_live.py

Cassettes are committed; secrets are redacted via conftest `vcr_config`.
"""

import jsonschema
import pytest

from dyor.ingestion.defillama import DefiLlamaClient
from tests.schemas import DEFILLAMA_PROTOCOL

pytestmark = [pytest.mark.integration, pytest.mark.vcr]


def test_protocols_carry_join_keys(sample_config):
    with DefiLlamaClient(sample_config, use_cache=False) as client:
        protocols = client.protocols()
    assert isinstance(protocols, list) and protocols
    sample = protocols[0]
    # the cross-source identity join keys must be present
    assert "gecko_id" in sample
    assert "slug" in sample
    jsonschema.validate(sample, DEFILLAMA_PROTOCOL)  # contract test — catches drift


def test_protocol_fees_shape(sample_config):
    with DefiLlamaClient(sample_config, use_cache=False) as client:
        fees = client.protocol_fees("aave")
    assert "total24h" in fees or "totalDataChart" in fees
