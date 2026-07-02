"""Unit tests for ingestion plumbing: caching + retry/backoff error paths.

Uses respx to mock httpx so we exercise 429/5xx retries and client-error
non-retries without touching the network. Backoff sleeps are patched to no-op so
the suite stays fast.
"""

import httpx
import pytest
import respx

from dyor.ingestion.base import BaseClient, FileCache, RateLimiter


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("dyor.ingestion.base.time.sleep", lambda *_: None)


@pytest.fixture
def client(tmp_path, monkeypatch, sample_config):
    # point the cache at a tmp dir so tests don't touch the real .cache
    monkeypatch.setattr("dyor.ingestion.base.PROJECT_ROOT", tmp_path)
    c = BaseClient(sample_config)
    yield c
    c.close()


def test_file_cache_roundtrip_and_ttl(tmp_path):
    cache = FileCache(tmp_path, ttl_seconds=100)
    assert cache.get("u", {"a": 1}) is None
    cache.set("u", {"a": 1}, {"ok": True})
    assert cache.get("u", {"a": 1}) == {"ok": True}
    # different params → different key → miss
    assert cache.get("u", {"a": 2}) is None


def test_expired_cache_is_missed(tmp_path):
    cache = FileCache(tmp_path, ttl_seconds=0)  # everything immediately stale
    cache.set("u", None, {"v": 1})
    assert cache.get("u", None) is None


@respx.mock
def test_retries_on_429_then_succeeds(client):
    route = respx.get("https://x.test/data").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    assert client.get_json("https://x.test/data") == {"ok": 1}
    assert route.call_count == 2


@respx.mock
def test_empty_200_body_is_none_not_retry(client):
    # DefiLlama /tvl/{slug} returns 200 with an empty body for a no-TVL protocol;
    # that's "no data" (None), not a parse error to retry into a failure.
    route = respx.get("https://x.test/empty").mock(return_value=httpx.Response(200, content=b""))
    assert client.get_json("https://x.test/empty") is None
    assert route.call_count == 1  # not retried


@respx.mock
def test_whitespace_200_body_is_none(client):
    route = respx.get("https://x.test/ws").mock(return_value=httpx.Response(200, content=b"  \n"))
    assert client.get_json("https://x.test/ws") is None
    assert route.call_count == 1


@respx.mock
def test_does_not_retry_client_error(client):
    respx.get("https://x.test/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        client.get_json("https://x.test/missing")


@respx.mock
def test_exhausts_retries_then_raises(client):
    respx.get("https://x.test/down").mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError, match="failed after"):
        client.get_json("https://x.test/down")


@respx.mock
def test_second_call_served_from_cache(client):
    route = respx.get("https://x.test/cached").mock(
        return_value=httpx.Response(200, json={"n": 1})
    )
    client.get_json("https://x.test/cached")
    client.get_json("https://x.test/cached")
    assert route.call_count == 1  # second call hit the on-disk cache


def test_rate_limiter_allows_burst_quickly():
    # a generous limiter should not block on the first acquire
    limiter = RateLimiter(rate_per_min=600)
    limiter.acquire()  # should return effectively immediately
