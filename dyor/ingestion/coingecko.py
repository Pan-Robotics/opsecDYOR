"""CoinGecko client — the identity hub + market data.

Keyless: ~30 calls/min on the public host, paced conservatively. Two kinds of
key exist and they look identical (`CG-…`), so the tier is configured, not
inferred (`DYOR_COINGECKO_API_TIER`):
  * demo — free key, PUBLIC host, header `x-cg-demo-api-key`
  * pro  — paid key, pro-api host, header `x-cg-pro-api-key`
Sending a demo key as a pro key 401s everywhere, which is the failure mode this
guards against.

The critical endpoint for entity resolution is `/coins/list?include_platform=true`,
which maps CoinGecko `id` → {symbol, name, platforms{chain→contract}}.

Note: CoinGecko platform IDs are STRINGS like "polygon-pos", not numeric EVM
chain IDs — `/asset_platforms` provides the mapping.
"""

from __future__ import annotations

from typing import Any

from dyor.config import get_settings
from dyor.ingestion.base import BaseClient

# One page of /coins/markets. More ids than this would have been silently
# truncated; `markets()` now pages.
_MARKETS_PAGE = 250
# Ids per /coins/markets call. The page cap is 250, but long id lists share one per-IP
# budget with everything else the app does, and a rejected call loses the whole page.
_MARKETS_CHUNK = 100

# Minimal coin-detail payload: identity, categories and sentiment only.
_MINIMAL_DETAIL = {
    "localization": "false", "tickers": "false", "market_data": "false",
    "community_data": "false", "developer_data": "false", "sparkline": "false",
}
# The collector's variant: market_data carries `total_value_locked` (a free TVL
# for tokens DefiLlama has no protocol for) and supply flags. developer_data /
# community_data are NOT requested — the free tier returns them as null (2026).
_META_DETAIL = {**_MINIMAL_DETAIL, "market_data": "true"}


def _tier() -> str:
    return (get_settings().coingecko_api_tier or "demo").lower()


class CoinGeckoClient(BaseClient):
    name = "coingecko"
    default_rate_per_min = 25.0

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        self._api_key = get_settings().coingecko_api_key
        self._pro = bool(self._api_key) and _tier() == "pro"
        if self._api_key and "rate_per_min" not in kwargs:
            kwargs["rate_per_min"] = 400.0 if self._pro else 30.0
        super().__init__(config, **kwargs)
        src = self.config["ingestion"]["sources"]["coingecko"]
        self.base_url = src["pro_base_url"] if self._pro else src["base_url"]

    retry_statuses = frozenset({429, 403})   # the edge answers 403 as well as 429 when the free budget is spent

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        key = get_settings().coingecko_api_key
        if key:
            headers["x-cg-pro-api-key" if _tier() == "pro" else "x-cg-demo-api-key"] = key
        return headers

    # -- identity (the join map) --------------------------------------------
    def coins_list(self, include_platform: bool = True) -> list[dict[str, Any]]:
        """id → {symbol, name, platforms}. The cross-chain identity backbone."""
        return self.get_json(
            f"{self.base_url}/coins/list",
            params={"include_platform": str(include_platform).lower()},
        )

    def asset_platforms(self) -> list[dict[str, Any]]:
        """Platform string-ID → chain metadata (incl. numeric chain_identifier)."""
        return self.get_json(f"{self.base_url}/asset_platforms")

    def coin_by_contract(self, platform_id: str, address: str) -> dict[str, Any]:
        """Resolve a `chain:address` to a CoinGecko coin (lowercase address).

        The returned detail carries the coin's cross-chain `platforms` map, so any
        one chain's address resolves to the unified token across every chain.
        """
        return self.get_json(
            f"{self.base_url}/coins/{platform_id}/contract/{address.lower()}"
        )

    def search(self, query: str) -> dict[str, Any]:
        """Free-text search by name or symbol → {coins: [{id, symbol, name, ...}]}."""
        return self.get_json(f"{self.base_url}/search", params={"query": query})

    def coin_detail(self, coin_id: str) -> dict[str, Any]:
        """Minimal coin detail (id, symbol, name, cross-chain `platforms`)."""
        return self.get_json(f"{self.base_url}/coins/{coin_id}", params=dict(_MINIMAL_DETAIL))

    # -- market data ---------------------------------------------------------
    def markets(self, ids: list[str], vs_currency: str = "usd") -> list[dict[str, Any]]:
        """Price, market cap, FDV, circulating/total supply, ATH, volume.

        Pages in chunks of 250 ids — the API's page cap — so a universe larger
        than one page is never silently truncated.
        """
        out: list[dict[str, Any]] = []
        for i in range(0, len(ids), _MARKETS_CHUNK):
            chunk = ids[i:i + _MARKETS_CHUNK]
            page = self.get_json(
                f"{self.base_url}/coins/markets",
                params={
                    "vs_currency": vs_currency,
                    "ids": ",".join(chunk),
                    "order": "market_cap_desc",
                    "per_page": _MARKETS_PAGE,
                    "page": 1,
                },
            )
            out.extend(page or [])
        return out

    # -- social (keyless) ----------------------------------------------------
    def coin_sentiment(self, coin_id: str) -> float | None:
        """CoinGecko up-vote sentiment for a coin, as a percent (0–100) or None.

        A coarse, keyless social signal (community up/down votes).
        """
        return self.coin_detail(coin_id).get("sentiment_votes_up_percentage")

    def coin_meta(self, coin_id: str) -> dict[str, Any]:
        """Everything the collector wants from one coin-detail call:

          sentiment        — up-vote %, coarse social signal
          categories       — drive asset-class classification
          tvl_usd          — CoinGecko's TVL; fallback when DefiLlama has no slug
          watchlist_users  — watchlist count; free, near-universal attention signal
          max_supply_infinite, github_repos — supply semantics / dev-org discovery
        """
        data = self.get_json(f"{self.base_url}/coins/{coin_id}", params=dict(_META_DETAIL))
        md = data.get("market_data") or {}
        repos = ((data.get("links") or {}).get("repos_url") or {}).get("github") or []
        return {
            "sentiment": data.get("sentiment_votes_up_percentage"),
            "categories": [c for c in (data.get("categories") or []) if c],
            "tvl_usd": (md.get("total_value_locked") or {}).get("usd"),
            "watchlist_users": data.get("watchlist_portfolio_users"),
            "max_supply_infinite": md.get("max_supply_infinite"),
            "github_repos": [r for r in repos if r],
        }

    def market_chart(self, coin_id: str, days: int = 30, vs_currency: str = "usd") -> dict[str, Any]:
        """Historical price series → {prices: [[ms, price], ...], market_caps, total_volumes}.

        Granularity is auto: 1 day → ~5-min, 2–90 → hourly, >90 → daily (free tier).
        """
        return self.get_json(
            f"{self.base_url}/coins/{coin_id}/market_chart",
            params={"vs_currency": vs_currency, "days": days},
        )

    # -- narratives ----------------------------------------------------------
    def categories(self) -> list[dict[str, Any]]:
        """500+ categories with market-cap + 24h change — the narrative tracker."""
        return self.get_json(f"{self.base_url}/coins/categories")
