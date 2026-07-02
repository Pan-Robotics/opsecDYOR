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

from dyor.config import get_settings, load_config
from dyor.ingestion.base import RateLimiter


class SantimentClient:
    name = "santiment"

    def __init__(self, config: dict | None = None) -> None:
        cfg = config if config is not None else load_config()
        src = cfg["ingestion"]["sources"]["santiment"]
        self.url = src["base_url"]
        self.limiter = RateLimiter(src["rate_limit_per_min"])
        headers = {"Content-Type": "application/json", "User-Agent": "dyor/0.1"}
        key = get_settings().santiment_api_key
        if key:
            headers["Authorization"] = f"Apikey {key}"
        self._client = httpx.Client(timeout=30.0, headers=headers)

    def query(self, graphql: str, variables: dict | None = None) -> dict[str, Any]:
        self.limiter.acquire()
        resp = self._client.post(
            self.url, json={"query": graphql, "variables": variables or {}}
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(f"santiment GraphQL error: {payload['errors']}")
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
        gql = self._TIMESERIES.format(interval=interval)
        data = self.query(gql, {
            "metric": metric, "slug": slug, "from": from_iso, "to": to_iso,
        })
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
