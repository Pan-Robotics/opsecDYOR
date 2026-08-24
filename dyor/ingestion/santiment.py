"""Santiment client — social + dev + on-chain via GraphQL (free entry point).

Free tier: 1000 calls/mo, 30-day history, 3000+ assets. GraphQL-only, so this
client POSTs queries rather than using the GET helpers in BaseClient. Auth is an
optional `Authorization: Apikey <key>` header (DYOR_SANTIMENT_API_KEY).

This is a thin stub: one generic `query()` plus a `social_volume` convenience
wrapper showing the metric-query shape. Extend with more `getMetric` calls as
the social/dev layer fills out.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from dyor.config import PROJECT_ROOT, get_settings, load_config
from dyor.ingestion.base import FileCache, RateLimiter

# gecko_id → Santiment slug where they differ. The collector's best-effort
# `santiment_slug = gecko_id` misses these (verified against Santiment's own
# allProjects list, 2026-08-24); two are L1 reference-basket members, so the
# mapping directly widens the anchored address-growth/dev distributions.
SLUG_OVERRIDES: dict[str, str] = {
    "polkadot": "polkadot-new",
    "starknet": "starknet-token",
    "tornado-cash": "torn",
    "quickswap": "p-quickswap-new",
    "benqi": "a-benqi",
    "bsquared-network": "bnb-bsquared-network",
    "veno-finance": "veno-finance-vno",
    "rain": "arb-rain",
}


class SantimentClient:
    name = "santiment"

    def __init__(self, config: dict | None = None, *, use_cache: bool = True) -> None:
        cfg = config if config is not None else load_config()
        ingestion = cfg["ingestion"]
        src = ingestion["sources"]["santiment"]
        self.url = src["base_url"]
        self.limiter = RateLimiter(src["rate_limit_per_min"])
        # The free tier is 1000 calls/MONTH — without a cache, every analyze
        # burns 2 of them live (~500 analyses/month for the whole service).
        # POSTs are cached on (url, query+variables), same TTL as the GETs.
        self.use_cache = use_cache
        self.cache = FileCache(
            PROJECT_ROOT / ingestion["cache_dir"] / self.name,
            ingestion["cache_ttl_seconds"],
        )
        # Only ~35% of our gecko_ids are Santiment slugs, so most calls fail with
        # "is not an existing slug" — and each failure still costs a call against
        # the ~1000/month free tier. Remember the misses for much longer than a
        # normal response: a slug that doesn't exist rarely starts existing, and
        # a stale miss self-corrects on the next expiry.
        self.miss_cache = FileCache(
            PROJECT_ROOT / ingestion["cache_dir"] / f"{self.name}-misses",
            src.get("miss_cache_ttl_seconds", 30 * 86400),
        )
        headers = {"Content-Type": "application/json", "User-Agent": "dyor/0.1"}
        key = get_settings().santiment_api_key
        if key:
            headers["Authorization"] = f"Apikey {key}"
        self._client = httpx.Client(timeout=30.0, headers=headers)

    def query(self, graphql: str, variables: dict | None = None) -> dict[str, Any]:
        cache_key = {"q": graphql, "v": variables or {}}
        if self.use_cache:
            cached = self.cache.get(self.url, cache_key)
            if cached is not None:
                return cached
        self.limiter.acquire()
        resp = self._client.post(
            self.url, json={"query": graphql, "variables": variables or {}}
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(f"santiment GraphQL error: {payload['errors']}")
        if self.use_cache:
            self.cache.set(self.url, cache_key, payload["data"])
        return payload["data"]

    # `interval` is a Santiment custom scalar; inline it as a literal (it's
    # internal, never user input) rather than risk a variable-type mismatch.
    _TIMESERIES = """
    query ($metric: String!, $slug: String!, $from: DateTime!, $to: DateTime!) {{
      getMetric(metric: $metric) {{
        timeseriesData(slug: $slug, from: $from, to: $to, interval: "{interval}") {{
          datetime
          value
        }}
      }}
    }}
    """

    def metric_timeseries(
        self,
        metric: str,
        slug: str,
        from_iso: str,
        to_iso: str,
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        """Generic Santiment metric time series → [{datetime, value}, ...].

        Free/anonymous access works for many on-chain + dev metrics (e.g.
        `daily_active_addresses`, `dev_activity`) but only within the last ~30
        days. Social metrics (`social_volume_total`) require a key.
        """
        miss_key = {"unsupported": [metric, slug]}
        if self.use_cache and self.miss_cache.get(self.url, miss_key) is not None:
            return []  # known-untracked slug — don't spend a call to be told again

        gql = self._TIMESERIES.format(interval=interval)
        try:
            data = self.query(gql, {
                "metric": metric, "slug": slug, "from": from_iso, "to": to_iso,
            })
        except RuntimeError as exc:
            # Remember only "this slug does not exist" — never a rate limit, a
            # quota exhaustion or a subscription restriction, which are
            # transient or key-dependent and must stay loud.
            if self.use_cache and "is not an existing slug" in str(exc):
                self.miss_cache.set(self.url, miss_key, True)
                return []
            raise
        return data["getMetric"]["timeseriesData"]

    def daily_active_addresses(self, slug: str, from_iso: str, to_iso: str) -> list[dict[str, Any]]:
        """On-chain usage trend (free/anonymous)."""
        return self.metric_timeseries("daily_active_addresses", slug, from_iso, to_iso)

    def dev_activity(self, slug: str, from_iso: str, to_iso: str) -> list[dict[str, Any]]:
        """Santiment's dev-activity metric — a richer dev signal than a single
        repo's last push (free/anonymous)."""
        return self.metric_timeseries("dev_activity", slug, from_iso, to_iso)

    def social_volume(self, slug: str, from_iso: str, to_iso: str) -> list[dict[str, Any]]:
        """Daily social volume (requires an API key — restricted anonymously)."""
        return self.metric_timeseries("social_volume_total", slug, from_iso, to_iso)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SantimentClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# Kept off the hot path: a tiny backoff helper for the manual POST flow above.
def _sleep_backoff(attempt: int, base: float = 1.0) -> None:
    time.sleep(base * (2**attempt))
