"""CoinGecko client — the identity hub + market data.

Free/Demo tier: ~30 calls/min, no key for basic endpoints. A Pro key (sent as
`x-cg-pro-api-key`) switches the host to pro-api and raises limits. The critical
endpoint for entity resolution is `/coins/list?include_platform=true`, which
maps CoinGecko `id` → {symbol, name, platforms{chain→contract}}.

Note: CoinGecko platform IDs are STRINGS like "polygon-pos", not numeric EVM
chain IDs — `/asset_platforms` provides the mapping.
"""

from __future__ import annotations

from typing import Any

from dyor.config import get_settings
from dyor.ingestion.base import BaseClient


class CoinGeckoClient(BaseClient):
    name = "coingecko"
    default_rate_per_min = 25.0

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        # A Pro key lifts the rate limit well above the conservative keyless pace.
        self._api_key = get_settings().coingecko_api_key
        if self._api_key and "rate_per_min" not in kwargs:
            kwargs["rate_per_min"] = 400.0
        super().__init__(config, **kwargs)
        src = self.config["ingestion"]["sources"]["coingecko"]
        self.base_url = src["pro_base_url"] if self._api_key else src["base_url"]

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        key = get_settings().coingecko_api_key
        if key:
            headers["x-cg-pro-api-key"] = key
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
        return self.get_json(
            f"{self.base_url}/coins/{coin_id}",
            params={
                "localization": "false", "tickers": "false", "market_data": "false",
                "community_data": "false", "developer_data": "false", "sparkline": "false",
            },
        )

    # -- market data ---------------------------------------------------------
    def markets(self, ids: list[str], vs_currency: str = "usd") -> list[dict[str, Any]]:
        """Price, market cap, FDV, circulating/total supply, ATH, volume."""
        return self.get_json(
            f"{self.base_url}/coins/markets",
            params={
                "vs_currency": vs_currency,
                "ids": ",".join(ids),
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
            },
        )

    # -- social (keyless) ----------------------------------------------------
    def coin_sentiment(self, coin_id: str) -> float | None:
        """CoinGecko up-vote sentiment for a coin, as a percent (0–100) or None.

        A coarse, keyless social signal (community up/down votes). Fetched with a
        minimal payload (no market/dev/ticker data) to keep the response small.
        """
        data = self.get_json(
            f"{self.base_url}/coins/{coin_id}",
            params={
                "localization": "false", "tickers": "false", "market_data": "false",
                "community_data": "false", "developer_data": "false", "sparkline": "false",
            },
        )
        return data.get("sentiment_votes_up_percentage")

    def coin_meta(self, coin_id: str) -> dict[str, Any]:
        """Sentiment + CoinGecko categories in one minimal coin-detail call.

        Same endpoint/params as `coin_sentiment`, so it reuses that cassette.
        Categories drive asset-class classification (DeFi vs L1 vs meme vs …).
        """
        data = self.get_json(
            f"{self.base_url}/coins/{coin_id}",
            params={
                "localization": "false", "tickers": "false", "market_data": "false",
                "community_data": "false", "developer_data": "false", "sparkline": "false",
            },
        )
        return {
            "sentiment": data.get("sentiment_votes_up_percentage"),
            "categories": [c for c in (data.get("categories") or []) if c],
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
