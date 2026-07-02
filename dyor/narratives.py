"""Narrative / sector rotation tracking via CoinGecko's 500+ categories.

The thesis docs' core idea: capital rotates between narratives (AI, DePIN,
RWA, privacy, gaming…), and the category endpoint is the practical instrument
for spotting which sector is heating. This module turns the raw
`/coins/categories` payload into a ranked rotation view.

`rank_categories` is pure (data in → data out), so it unit-tests on fixtures;
`fetch_narratives` does the network call.
"""

from __future__ import annotations

from typing import Any

from dyor.config import load_config
from dyor.ingestion.coingecko import CoinGeckoClient


def rank_categories(
    categories: list[dict[str, Any]],
    by: str = "market_cap_change_24h",
    top: int | None = 25,
    min_market_cap: float = 50_000_000,
) -> list[dict[str, Any]]:
    """Rank narratives by momentum. Returns a trimmed, normalized view.

    Filters out micro-cap categories (noise) and rows missing the sort key, then
    sorts descending so the hottest sector is first. `by` is typically
    `market_cap_change_24h` (momentum) but can be `market_cap` or `volume_24h`.
    """
    out_key = by_key(by)
    rows = []
    for cat in categories:
        sort_val = cat.get(by)
        mcap = cat.get("market_cap")
        if sort_val is None or mcap is None or mcap < min_market_cap:
            continue
        rows.append({
            "name": cat.get("name"),
            "market_cap": mcap,
            "change_24h": cat.get("market_cap_change_24h"),
            "volume_24h": cat.get("volume_24h"),
            "top_3": list(cat.get("top_3_coins_id") or [])[:3],
        })
    rows.sort(key=lambda r: (r.get(out_key) is None, -(r.get(out_key) or 0)))
    return rows[:top] if top else rows


def by_key(by: str) -> str:
    """Map a sort field to the key used in the normalized row dict."""
    return {
        "market_cap_change_24h": "change_24h",
        "market_cap": "market_cap",
        "volume_24h": "volume_24h",
    }.get(by, "change_24h")


def fetch_narratives(
    config: dict | None = None, *, use_cache: bool = True, **rank_kwargs
) -> list[dict[str, Any]]:
    """Fetch CoinGecko categories and return the ranked rotation view."""
    cfg = config if config is not None else load_config()
    with CoinGeckoClient(cfg, use_cache=use_cache) as cg:
        categories = cg.categories()
    return rank_categories(categories, **rank_kwargs)
