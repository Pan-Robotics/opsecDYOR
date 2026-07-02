"""Resolve a free-text query to a canonical token identity.

A user can search by:
  * name           — "Aave", "Lido DAO"
  * symbol         — "AAVE", "uni"
  * contract address — EVM `0x…` or Solana base58; resolves the unified token
                       across ALL its chains (CoinGecko's coin id aggregates
                       every chain deployment).

`resolve_query` returns a `ResolvedToken` (or None). The classification of the
query (address vs name/symbol) is pure and unit-tested; the lookups hit
CoinGecko search / contract endpoints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dyor.config import load_config

_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_SOLANA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

# EVM chains tried (in order) when resolving a bare 0x address with no chain hint.
_EVM_PLATFORMS = [
    "ethereum", "binance-smart-chain", "polygon-pos", "arbitrum-one",
    "base", "optimistic-ethereum", "avalanche",
]


# Block-explorer "token page" templates for building per-chain links.
CHAIN_EXPLORERS: dict[str, str] = {
    "ethereum": "https://etherscan.io/token/{addr}",
    "binance-smart-chain": "https://bscscan.com/token/{addr}",
    "polygon-pos": "https://polygonscan.com/token/{addr}",
    "arbitrum-one": "https://arbiscan.io/token/{addr}",
    "base": "https://basescan.org/token/{addr}",
    "optimistic-ethereum": "https://optimistic.etherscan.io/token/{addr}",
    "avalanche": "https://snowtrace.io/token/{addr}",
    "solana": "https://solscan.io/token/{addr}",
}


@dataclass(frozen=True)
class ResolvedToken:
    gecko_id: str
    symbol: str
    name: str
    platforms: dict[str, str] = field(default_factory=dict)  # chain -> address
    market_cap_rank: int | None = None
    matched_by: str = "name"  # "name" | "symbol" | "address" | "id"
    query: str = ""
    links: dict[str, Any] = field(default_factory=dict)  # homepage/twitter/github/explorers

    @property
    def chains(self) -> list[str]:
        return [c for c, a in self.platforms.items() if a]

    @property
    def coingecko_url(self) -> str:
        return f"https://www.coingecko.com/en/coins/{self.gecko_id}"

    def explorer_links(self) -> dict[str, str]:
        """chain -> block-explorer token page, for the chains we know explorers for."""
        out = {}
        for chain, addr in self.platforms.items():
            tmpl = CHAIN_EXPLORERS.get(chain)
            if tmpl and addr:
                out[chain] = tmpl.format(addr=addr)
        return out


def classify_query(query: str) -> str:
    """'address' (EVM/Solana) or 'text' (name/symbol). Pure."""
    q = query.strip()
    if _EVM_RE.match(q):
        return "address"
    if not q.startswith("0x") and _SOLANA_RE.match(q):
        return "address"
    return "text"


def _extract_links(detail: dict[str, Any]) -> dict[str, Any]:
    """Pull the full set of web + social links from a CoinGecko coin detail."""
    raw = detail.get("links") or {}

    def first(seq):
        return next((u for u in (seq or []) if u), None)

    chats = [u for u in (raw.get("chat_url") or []) if u]
    discord = next((u for u in chats if "discord" in u.lower()), None)
    tg_id = raw.get("telegram_channel_identifier")
    telegram = (f"https://t.me/{tg_id}" if tg_id
                else next((u for u in chats if "t.me" in u.lower() or "telegram" in u.lower()), None))
    return {
        "homepage": first(raw.get("homepage")),
        "github": first((raw.get("repos_url") or {}).get("github")),
        "twitter": (f"https://x.com/{raw['twitter_screen_name']}"
                    if raw.get("twitter_screen_name") else None),
        "reddit": raw.get("subreddit_url") or None,
        "telegram": telegram,
        "discord": discord,
        "whitepaper": raw.get("whitepaper") or None,
        "explorers": [u for u in (raw.get("blockchain_site") or []) if u][:4],
    }


def _from_coin_detail(detail: dict[str, Any], *, matched_by: str, query: str) -> ResolvedToken:
    platforms = {c: a for c, a in (detail.get("platforms") or {}).items() if c and a}
    return ResolvedToken(
        gecko_id=detail["id"], symbol=(detail.get("symbol") or "").upper(),
        name=detail.get("name") or detail["id"], platforms=platforms,
        market_cap_rank=detail.get("market_cap_rank"), matched_by=matched_by, query=query,
        links=_extract_links(detail),
    )


def _best_search_hit(coins: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    """Pick the best search result.

    Among coins whose symbol, name, OR id exactly matches the query, pick the one
    with the best (lowest) market-cap rank — so "bitcoin" resolves to Bitcoin
    (name, rank 1), NOT a memecoin whose *symbol* happens to be "BITCOIN" (rank
    ~3000). Falls back to the highest-cap search result when nothing matches
    exactly.
    """
    if not coins:
        return None
    q = query.strip().lower()

    def rank(c):  # missing rank sorts last
        return c.get("market_cap_rank") or 10**9

    exact = [c for c in coins
             if q in {(c.get("symbol") or "").lower(), (c.get("name") or "").lower(),
                      (c.get("id") or "").lower()}]
    return min(exact, key=rank) if exact else min(coins, key=rank)


def resolve_query(
    query: str, config: dict | None = None, *, use_cache: bool = True, client=None
) -> ResolvedToken | None:
    """Resolve a name/symbol/address to a `ResolvedToken`, or None if not found."""
    cfg = config if config is not None else load_config()
    own_client = client is None
    if own_client:
        from dyor.ingestion.coingecko import CoinGeckoClient
        client = CoinGeckoClient(cfg, use_cache=use_cache)

    try:
        q = query.strip()
        if classify_query(q) == "address":
            platforms = ["solana"] if not q.startswith("0x") else _EVM_PLATFORMS
            for platform in platforms:
                try:
                    detail = client.coin_by_contract(platform, q)
                except Exception:
                    continue
                if detail and detail.get("id"):
                    return _from_coin_detail(detail, matched_by="address", query=query)
            return None

        # name / symbol
        hit = _best_search_hit(client.search(q).get("coins", []), q)
        if not hit:
            # the query may itself be a CoinGecko id (e.g. "usd-coin")
            try:
                detail = client.coin_detail(q)
                if detail.get("id"):
                    return _from_coin_detail(detail, matched_by="id", query=query)
            except Exception:
                pass
            return None
        detail = client.coin_detail(hit["id"])
        matched = "symbol" if (hit.get("symbol") or "").lower() == q.lower() else "name"
        return _from_coin_detail(detail, matched_by=matched, query=query)
    finally:
        if own_client:
            client.close()
