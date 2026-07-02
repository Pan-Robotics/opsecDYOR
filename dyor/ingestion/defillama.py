"""DefiLlama client — the free foundation of the build.

No API key, no hard rate limit for normal traffic. Spread across four hosts:
  api.llama.fi          protocols / tvl / fees / revenue
  coins.llama.fi        prices keyed by chain:address (the identity-join host)
  stablecoins.llama.fi  stablecoin supply
  yields.llama.fi       pools / APYs

Each protocol object carries `gecko_id` and `cmcId` — the cross-source join keys.
"""

from __future__ import annotations

from typing import Any

from dyor.config import get_settings
from dyor.ingestion.base import BaseClient

PRO_BASE = "https://pro-api.llama.fi"


class DefiLlamaClient(BaseClient):
    name = "defillama"
    default_rate_per_min = 120.0

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        super().__init__(config, **kwargs)
        self.urls = self.config["ingestion"]["sources"]["defillama"]["base_urls"]
        self._pro_key = get_settings().defillama_api_key

    @property
    def has_pro(self) -> bool:
        return bool(self._pro_key)

    # -- protocols / tvl -----------------------------------------------------
    def protocols(self) -> list[dict[str, Any]]:
        """All protocols with TVL + `gecko_id`/`cmcId` join keys."""
        return self.get_json(f"{self.urls['api']}/protocols")

    def protocol(self, slug: str) -> dict[str, Any]:
        """Full detail for one protocol (historical TVL by chain, token info)."""
        return self.get_json(f"{self.urls['api']}/protocol/{slug}")

    # -- fees / revenue (the fundamentals layer) -----------------------------
    def fees_overview(self) -> dict[str, Any]:
        """All-protocol fees + revenue summary."""
        return self.get_json(
            f"{self.urls['api']}/overview/fees",
            params={"dataType": "dailyFees"},
        )

    def fees_summary(self, slug: str, data_type: str | None = None) -> dict[str, Any]:
        """Per-protocol fees/revenue summary (total24h/7d/30d/1y).

        `data_type` selects the series: None → dailyFees (default), or one of
        'dailyRevenue', 'dailyHoldersRevenue'. Use to annualize for P/F, P/S,
        and real yield.
        """
        params = {"dataType": data_type} if data_type else None
        return self.get_json(f"{self.urls['api']}/summary/fees/{slug}", params=params)

    def protocol_fees(self, slug: str) -> dict[str, Any]:
        """Default (dailyFees) summary — kept as a thin alias of fees_summary."""
        return self.fees_summary(slug)

    def tvl(self, slug: str) -> float:
        """Current TVL for a protocol (bare number). Used for MC/TVL."""
        return self.get_json(f"{self.urls['api']}/tvl/{slug}")

    # -- prices keyed on chain:address (identity host) -----------------------
    def prices_current(self, chain_addresses: list[str]) -> dict[str, Any]:
        """Current prices for `chain:address` keys, e.g. 'ethereum:0xA0b8...'.

        Returns per-coin price + a confidence score (0–1) and optional redirect.
        """
        joined = ",".join(chain_addresses)
        return self.get_json(f"{self.urls['coins']}/prices/current/{joined}")

    # -- unlocks / emissions (PRO — 402 on the free tier) --------------------
    def emissions(self, protocol: str) -> dict[str, Any]:
        """Per-protocol unlock/vesting schedule. Requires a DefiLlama Pro key
        (DYOR_DEFILLAMA_API_KEY); the free endpoint returns 402.

        Guard calls with `client.has_pro` — the collector only invokes this when
        a key is configured, so the free path makes no wasted 402 request.
        """
        if not self._pro_key:
            raise RuntimeError(
                "DefiLlama emissions is a Pro endpoint — set DYOR_DEFILLAMA_API_KEY"
            )
        return self.get_json(f"{PRO_BASE}/{self._pro_key}/api/emissions/{protocol}")

    # -- stablecoins ---------------------------------------------------------
    def stablecoins(self) -> dict[str, Any]:
        return self.get_json(
            f"{self.urls['stablecoins']}/stablecoins",
            params={"includePrices": "true"},
        )
