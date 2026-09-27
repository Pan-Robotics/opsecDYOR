"""The reference anchor must never silently disappear (2026-09-27).

Under API concurrency the anchor loader opened a read-write DuckDB connection
while request threads held read-only ones; DuckDB refused, the error was
swallowed, and the request scored every token UNANCHORED — the same token came
back 54.8 on one call and 58.5 on the next. These tests pin the fixes: readers
open read-only, a transient failure is retried and then served from the last
good anchor, and a cold failure raises instead of changing scale."""

from __future__ import annotations

import pytest

from dyor import pipeline, reference
from dyor.reference import ReferenceUnavailable
from dyor.store import db


@pytest.fixture(autouse=True)
def _fresh_cache():
    reference.clear_distribution_cache()
    yield
    reference.clear_distribution_cache()


def test_reference_readers_open_read_only(monkeypatch):
    seen: list[bool] = []
    real = db.connect

    def spy(path=None, *, read_only=False):
        seen.append(read_only)
        return real(path, read_only=read_only)
    monkeypatch.setattr("dyor.store.db.connect", spy)
    reference.reference_peers("defi")
    reference._basket_version("defi")
    assert seen and all(seen), seen


def test_transient_failure_is_retried_then_served(monkeypatch):
    calls = {"n": 0}
    good = {"float_ratio": [0.5, 0.9]}

    def flaky(asset_class):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ReferenceUnavailable("lock contention")
        return good
    import time
    monkeypatch.setattr("dyor.reference.reference_distributions", flaky)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert pipeline._load_reference_dist({"defi"}) == {"defi": good}
    assert calls["n"] == 2


def test_persistent_cold_failure_raises_not_unanchored(monkeypatch):
    def broken(asset_class):
        raise ReferenceUnavailable("db locked")
    monkeypatch.setattr("dyor.reference.reference_distributions", broken)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(ReferenceUnavailable):
        pipeline._load_reference_dist({"defi"}, attempts=2)


def test_last_good_anchor_survives_a_read_failure(monkeypatch):
    good = {"float_ratio": __import__("numpy").asarray([0.5, 0.9])}
    def fake_dist(c, v):
        return good
    fake_dist.cache_clear = lambda: None          # stands in for the lru-cached loader
    monkeypatch.setattr("dyor.reference._basket_version", lambda c: "v1")
    monkeypatch.setattr("dyor.reference._distributions_for", fake_dist)
    assert reference.reference_distributions("meme") is good
    # the next version lookup fails (a writer holds the lock) → keep serving v1

    def boom(c):
        raise RuntimeError("Can't open a connection to same database file with a different configuration")
    monkeypatch.setattr("dyor.reference._basket_version", boom)
    assert reference.reference_distributions("meme") is good
    # a class never loaded in this process has nothing to fall back on
    with pytest.raises(ReferenceUnavailable):
        reference.reference_distributions("l1")


def test_no_basket_is_still_relative_not_an_error(sample_config):
    """A class with no stored basket → empty dist → relative normalization, as documented."""
    recs = [{"token": "a", "_class": "general", "price_to_fees": 5.0},
            {"token": "b", "_class": "general", "price_to_fees": 50.0}]
    res = {r.token: r for r in pipeline.score_universe(recs, sample_config, reference_anchored=True)}
    assert res["a"].final_score >= res["b"].final_score


def test_santiment_budget_exhaustion_short_circuits(monkeypatch, sample_config):
    """A 429 that says 'try again in 3 days' is the MONTHLY budget: stop calling."""
    import httpx

    from dyor.ingestion import santiment

    santiment.SantimentClient._exhausted_until = 0.0
    cl = santiment.SantimentClient(sample_config, use_cache=False)
    body = ('{"errors":{"details":"API Rate Limit Reached. Try again in 287179 seconds '
            '(3 days, 7 hours, 46 minutes, 19 seconds)."}}')
    posts = {"n": 0}

    def fake_post(url, json=None):
        posts["n"] += 1
        return httpx.Response(429, text=body, request=httpx.Request("POST", url))
    monkeypatch.setattr(cl._client, "post", fake_post)
    monkeypatch.setattr(cl.limiter, "acquire", lambda: None)
    with pytest.raises(santiment.SantimentBudgetExhausted):
        cl.dev_activity("bitcoin", "2026-09-01T00:00:00+00:00", "2026-09-28T00:00:00+00:00")
    with pytest.raises(santiment.SantimentBudgetExhausted):
        cl.daily_active_addresses("ethereum", "2026-09-01T00:00:00+00:00", "2026-09-28T00:00:00+00:00")
    assert posts["n"] == 1                       # the second call never hit the network
    assert santiment._rate_limit_wait_seconds(body) == 287179
    assert santiment._rate_limit_wait_seconds("Try again in 12 seconds") == 12
    assert santiment._rate_limit_wait_seconds("nope") is None
    # a per-minute 429 (short wait) is NOT treated as exhaustion
    santiment.SantimentClient._exhausted_until = 0.0
    short = '{"errors":{"details":"API Rate Limit Reached. Try again in 40 seconds"}}'
    monkeypatch.setattr(cl._client, "post", lambda url, json=None: httpx.Response(429, text=short, request=httpx.Request("POST", url)))
    with pytest.raises(httpx.HTTPStatusError):
        cl.dev_activity("bitcoin", "2026-09-01T00:00:00+00:00", "2026-09-28T00:00:00+00:00")
    assert santiment.SantimentClient._exhausted_until == 0.0
    cl.close()
