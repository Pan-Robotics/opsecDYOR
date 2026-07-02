"""Shared pytest fixtures + VCR configuration.

Cassettes live in tests/cassettes/. API keys are redacted from recordings so no
secret is ever committed. Integration tests (which use these cassettes) are
opt-in via the `integration` marker (see pyproject `addopts`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

CASSETTE_DIR = Path(__file__).parent / "cassettes"


@pytest.fixture(autouse=True)
def _no_ratelimit_sleep(monkeypatch):
    """Rate-limit + backoff sleeps are pointless against cassettes / pure
    functions — skip them so the suite (esp. integration replay) stays fast."""
    monkeypatch.setattr("dyor.ingestion.base.time.sleep", lambda *_: None)


@pytest.fixture(scope="module")
def vcr_config():
    # NOTE: record_mode is intentionally NOT set here — pytest-recording owns it
    # via the --record-mode CLI flag (default "none", so CI fails on unseen
    # requests). Setting it here would override the flag and block recording.
    return {
        "cassette_library_dir": str(CASSETTE_DIR),
        "filter_headers": [
            "authorization",
            "x-cg-pro-api-key",
            "x-messari-api-key",
            "cg-api-key",
            "x-api-key",
        ],
        "filter_query_parameters": ["api_key", "x_cg_pro_api_key"],
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
    }


@pytest.fixture
def sample_config():
    """Load the real config.yaml for tests that need weights/thresholds."""
    from dyor.config import load_config

    return load_config()
