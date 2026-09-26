"""Ingestion-layer hardening from the 2026-09-26 review.

Each test pins one defect: shared/thread-safe rate limiter, atomic cache with
eviction and empty-body caching, secret redaction, CoinGecko tier + pagination,
GitHub unauthenticated pacing, Ethplorer HTTP-200 errors, CryptoRank v3.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from dyor.config import Settings


# --- base: limiter + cache ---------------------------------------------------

def test_clients_share_one_limiter_per_source(sample_config):
    from dyor.ingestion.defillama import DefiLlamaClient

    a, b = DefiLlamaClient(sample_config), DefiLlamaClient(sample_config)
    assert a.limiter is b.limiter        # one bucket per (source, rate) per process
    a.close(); b.close()


def test_rate_limiter_is_thread_safe_under_contention(monkeypatch):
    from dyor.ingestion import base

    sleeps: list[float] = []
    monkeypatch.setattr(base.time, "sleep", lambda s: sleeps.append(s))
    lim = base.RateLimiter(rate_per_min=60, burst=1)   # 1 token, 1/sec refill
    errors: list[BaseException] = []

    def hit():
        try:
            for _ in range(20):
                lim.acquire()
        except BaseException as e:
            errors.append(e)

    ts = [threading.Thread(target=hit) for _ in range(8)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert not errors
    assert lim._tokens <= lim.capacity       # bucket never over-filled by a race


def test_file_cache_write_is_atomic_and_evicts_expired(tmp_path):
    from dyor.ingestion.base import FileCache

    c = FileCache(tmp_path, ttl_seconds=100)
    c.set("u", {"a": 1}, {"v": 1})
    assert not [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]   # no temp left behind
    assert c.get("u", {"a": 1}) == {"v": 1}
    stale = tmp_path / "stale.json"; stale.write_text("{}")
    old = time.time() - 1000
    import os; os.utime(stale, (old, old))
    (tmp_path / ".junk.tmp").write_text("x")
    assert c.evict_expired() == 2
    assert c.get("u", {"a": 1}) == {"v": 1}


def test_empty_body_is_cached_as_a_hit(sample_config, monkeypatch):
    """DefiLlama returns an empty 200 for a no-TVL protocol; that answer is data
    and must not be refetched on every collect."""
    from dyor.ingestion.defillama import DefiLlamaClient

    calls = {"n": 0}
    cl = DefiLlamaClient(sample_config)
    def fake(url, params):
        calls["n"] += 1
        return None
    monkeypatch.setattr(cl, "_request_with_retry", fake)
    assert cl.tvl("nothing") is None
    assert cl.tvl("nothing") is None
    cl.close()
    assert calls["n"] == 1


def test_secrets_are_redacted_from_error_text(monkeypatch):
    from dyor import config

    fake = Settings(defillama_api_key="SUPERSECRETKEY123", _env_file=None)
    monkeypatch.setattr(config, "get_settings", lambda: fake)
    msg = config.redact_secrets("GET https://pro-api.llama.fi/SUPERSECRETKEY123/api/emissions/x failed")
    assert "SUPERSECRETKEY123" not in msg and "***" in msg


# --- coingecko -----------------------------------------------------------------

def _cg(monkeypatch, sample_config, **settings):
    from dyor.ingestion import coingecko
    fake = Settings(_env_file=None, **settings)
    monkeypatch.setattr(coingecko, "get_settings", lambda: fake)
    return coingecko.CoinGeckoClient(sample_config)


def test_coingecko_demo_key_uses_public_host_and_demo_header(monkeypatch, sample_config):
    cl = _cg(monkeypatch, sample_config, coingecko_api_key="CG-demo", coingecko_api_tier="demo")
    assert "pro-api" not in cl.base_url
    assert cl._client.headers.get("x-cg-demo-api-key") == "CG-demo"
    assert "x-cg-pro-api-key" not in cl._client.headers
    cl.close()


def test_coingecko_pro_key_uses_pro_host_and_pro_header(monkeypatch, sample_config):
    cl = _cg(monkeypatch, sample_config, coingecko_api_key="CG-pro", coingecko_api_tier="pro")
    assert "pro-api" in cl.base_url
    assert cl._client.headers.get("x-cg-pro-api-key") == "CG-pro"
    cl.close()


def test_coingecko_markets_pages_past_250_ids(monkeypatch, sample_config):
    cl = _cg(monkeypatch, sample_config)
    seen: list[str] = []
    def fake(url, params=None):
        ids = params["ids"].split(",")
        seen.append(len(ids))
        return [{"id": i} for i in ids]
    monkeypatch.setattr(cl, "get_json", fake)
    rows = cl.markets([f"t{i}" for i in range(601)])
    cl.close()
    assert seen == [250, 250, 101] and len(rows) == 601


# --- github ----------------------------------------------------------------------

def test_github_paces_at_60_per_hour_without_a_token(monkeypatch, sample_config):
    from dyor.ingestion import github
    monkeypatch.setattr(github, "get_settings", lambda: Settings(_env_file=None))
    cl = github.GitHubClient(sample_config)
    assert cl.limiter.rate_per_min == pytest.approx(1.0)
    cl.close()
    monkeypatch.setattr(github, "get_settings", lambda: Settings(github_token="ghp_x", _env_file=None))
    cl = github.GitHubClient(sample_config)
    assert cl.limiter.rate_per_min > 1.0
    cl.close()


# --- ethplorer -------------------------------------------------------------------

def test_ethplorer_http200_error_body_raises(monkeypatch, sample_config):
    """freekey rate limits come back as 200 + {"error": ...}; that is a feed
    error, not 'no holders'."""
    from dyor.ingestion.ethplorer import EthplorerClient

    cl = EthplorerClient(sample_config)
    monkeypatch.setattr(cl, "get_json", lambda *a, **k: {"error": {"code": 133, "message": "rate limit"}})
    with pytest.raises(RuntimeError, match="133"):
        cl.top_token_holders("0xabc")
    monkeypatch.setattr(cl, "get_json", lambda *a, **k: {"holders": [{"share": 1.0}]})
    assert cl.top_token_holders("0xabc") == [{"share": 1.0}]
    cl.close()


# --- cryptorank ------------------------------------------------------------------

def _cr(monkeypatch, sample_config, key, endpoints):
    from dyor.ingestion import cryptorank
    fake = Settings(cryptorank_api_key=key, _env_file=None)
    monkeypatch.setattr(cryptorank, "get_settings", lambda: fake)
    cl = cryptorank.CryptoRankClient(sample_config)
    routes = {
        "/v3/status": {"data": {"plan": "Sandbox", "endpoints": endpoints}},
        "/v3/currencies/map": {"data": [{"id": 23773, "slug": "aave", "symbol": "AAVE", "name": "Aave"}]},
        "/v3/currencies/23773": {"data": {"circulatingSupply": 15_000_000, "totalSupply": 16_000_000,
                                          "maxSupply": 16_000_000}},
        "/v3/currencies/23773/vesting/allocations": {"data": [
            {"allocationName": "Team", "totalTokens": 4_000_000, "lockedTokens": 1_000_000}]},
        "/v3/currencies/23773/vesting/events": {"data": [{"time": "2027-01-01", "unlockValue": 2_500_000}]},
    }
    def fake_get(url, params=None):
        for path, body in routes.items():
            if url.endswith(path):
                return json.loads(json.dumps(body))
        raise AssertionError(f"unexpected {url}")
    monkeypatch.setattr(cl, "get_json", fake_get)
    return cl


def test_cryptorank_sandbox_plan_disables_feed_without_spending_credits(monkeypatch, sample_config):
    cl = _cr(monkeypatch, sample_config, "k", ["/v3/currencies/{id}", "/v3/currencies/map"])
    assert cl.enabled is False and "Sandbox" in (cl.disabled_reason or "")
    cl.close()


def test_cryptorank_pro_plan_yields_vesting_and_next_unlock(monkeypatch, sample_config):
    from dyor.metrics import tokenomics

    cl = _cr(monkeypatch, sample_config, "k",
             ["/v3/currencies/{id}", "/v3/currencies/map", "/v3/currencies/{id}/vesting/allocations"])
    assert cl.enabled is True
    coin = cl.coin("aave")
    assert coin["hasVesting"] is True and coin["nextUnlockUsd"] == 2_500_000
    assert tokenomics.unlock_overhang(coin["availableSupply"], coin["maxSupply"], coin["hasVesting"]) == pytest.approx(0.0625)
    with pytest.raises(LookupError, match="not found"):
        cl.coin("no-such-slug")
    cl.close()


def test_cryptorank_keyless_uses_config_flag(monkeypatch, sample_config):
    from dyor.ingestion import cryptorank
    monkeypatch.setattr(cryptorank, "get_settings", lambda: Settings(_env_file=None))
    cfg = json.loads(json.dumps(sample_config))
    cfg["ingestion"]["sources"]["cryptorank"] = {"enabled": False}
    cl = cryptorank.CryptoRankClient(cfg)
    assert cl.enabled is False and "disabled in config" in cl.disabled_reason
    cl.close()


def test_santiment_cache_evicts_expired_entries_on_init(tmp_path, monkeypatch, sample_config):
    """SantimentClient bypasses BaseClient, so eviction must be wired explicitly —
    its positive cache grew ~230 files/week forever on the server."""
    import os

    from dyor.ingestion import base, santiment as san_mod

    monkeypatch.setattr(san_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(base, "_EVICTED_DIRS", set())
    d = tmp_path / sample_config["ingestion"]["cache_dir"] / "santiment"
    d.mkdir(parents=True)
    stale = d / "old.json"; stale.write_text("{}")
    t = 0
    os.utime(stale, (t, t))
    fresh = d / "new.json"; fresh.write_text("{}")
    san_mod.SantimentClient(sample_config).close()
    assert not stale.exists() and fresh.exists()
