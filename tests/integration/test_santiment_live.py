"""Cassette-replayed integration tests for the Santiment client. OPT-IN.

`daily_active_addresses` and `dev_activity` work on Santiment's free/anonymous
tier (no key) within the last ~30 days. Fixed from/to dates are used so the
recorded GraphQL request body matches exactly on replay. See
test_defillama_live.py for the record/replay workflow.
"""

import pytest

from dyor.ingestion.santiment import SantimentClient

pytestmark = [pytest.mark.integration, pytest.mark.vcr]

# Fixed window inside the free 30-day horizon at record time. Replay is
# date-agnostic (it just matches the recorded request), so these never go stale.
FROM = "2026-05-25T00:00:00+00:00"
TO = "2026-06-18T00:00:00+00:00"


def test_daily_active_addresses(sample_config):
    with SantimentClient(sample_config, use_cache=False) as client:
        series = client.daily_active_addresses("aave", FROM, TO)
    assert isinstance(series, list) and series
    assert {"datetime", "value"} <= set(series[0])


def test_dev_activity(sample_config):
    with SantimentClient(sample_config, use_cache=False) as client:
        series = client.dev_activity("aave", FROM, TO)
    assert isinstance(series, list) and series
    assert {"datetime", "value"} <= set(series[0])
