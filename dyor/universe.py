"""Universe builder — turn DefiLlama's protocol list into scoring Targets.

Instead of hand-mapping a handful of tokens, build a universe automatically:
take the top-N protocols by TVL (optionally within a category), keep only those
with a CoinGecko `gecko_id` (so market data exists), and **auto-resolve** the
optional ids:

  * defillama_slug  — the protocol's own slug
  * eth_contract    — from CoinGecko `/coins/list` platforms (one call, all coins)
  * santiment_slug / cryptorank_key — best-effort = gecko_id (misses degrade to
    honest n/a via the collector's diagnostics, never a fabricated value)
  * category        — the DefiLlama category, used as the peer group

`targets_from_protocols` is pure (data in → Targets out) so it unit-tests on
fixtures; `fetch_universe` does the two network calls.
"""

from __future__ import annotations

from typing import Any, Iterable

from dyor.collect import Target
from dyor.config import load_config

# Categories that aren't protocol tokens we score the same way.
DEFAULT_EXCLUDE = frozenset({"CEX", "Chain", "Bridge"})


def eth_contracts_from_coins_list(coins_list: Iterable[dict[str, Any]]) -> dict[str, str]:
    """{gecko_id: lowercased Ethereum contract} from `/coins/list?include_platform`."""
    out: dict[str, str] = {}
    for coin in coins_list:
        addr = (coin.get("platforms") or {}).get("ethereum")
        if coin.get("id") and addr:
            out[coin["id"]] = addr.strip().lower()
    return out


def targets_from_protocols(
    protocols: Iterable[dict[str, Any]],
    eth_contracts: dict[str, str] | None = None,
    *,
    top_n: int = 50,
    category: str | None = None,
    exclude_categories: frozenset[str] = DEFAULT_EXCLUDE,
) -> list[Target]:
    """Top-N protocols by TVL → auto-resolved Targets.

    Keeps only protocols with a `gecko_id`; optionally restricts to one category.
    De-dupes by gecko_id (a token can run several protocols) keeping highest TVL.
    """
    eth_contracts = eth_contracts or {}

    best: dict[str, dict[str, Any]] = {}
    for p in protocols:
        gid = p.get("gecko_id")
        if not gid:
            continue
        cat = p.get("category")
        if cat in exclude_categories:
            continue
        if category and cat != category:
            continue
        tvl = p.get("tvl") or 0
        if gid not in best or tvl > (best[gid].get("tvl") or 0):
            best[gid] = p

    ranked = sorted(best.values(), key=lambda p: p.get("tvl") or 0, reverse=True)[:top_n]

    return [
        Target(
            gecko_id=p["gecko_id"],
            defillama_slug=p.get("slug"),
            github_org=None,                       # not cheaply auto-derivable
            santiment_slug=p["gecko_id"],          # best-effort
            cryptorank_key=p["gecko_id"],          # best-effort
            eth_contract=eth_contracts.get(p["gecko_id"]),
            category=p.get("category"),
        )
        for p in ranked
    ]


def basket_targets(
    protocols: Iterable[dict[str, Any]],
    eth_contracts: dict[str, str] | None = None,
    *,
    classes: Iterable[str] | None = None,
) -> list[Target]:
    """Targets for every token in the class reference baskets (pure).

    TVL rank alone yields a DeFi-only universe that churns week to week — a
    2026-08-24 refresh dropped ethereum, chainlink and celestia and left one L1
    and no memecoins. Pinning the baskets in keeps the majors and every asset
    class present, and makes the screener's composition stable across runs.
    """
    from dyor.classes import REFERENCE_BASKETS

    eth_contracts = eth_contracts or {}
    by_gecko = {p["gecko_id"]: p for p in protocols if p.get("gecko_id")}
    wanted = list(classes) if classes is not None else list(REFERENCE_BASKETS)

    seen: dict[str, Target] = {}
    for cls in wanted:
        for gid in REFERENCE_BASKETS.get(cls, []):
            if gid in seen:
                continue
            p = by_gecko.get(gid, {})
            seen[gid] = Target(
                gecko_id=gid,
                defillama_slug=p.get("slug"),
                santiment_slug=gid,
                cryptorank_key=gid,
                eth_contract=eth_contracts.get(gid),
                category=p.get("category"),
            )
    return list(seen.values())


def fetch_universe(
    config: dict | None = None,
    *,
    top_n: int = 50,
    category: str | None = None,
    use_cache: bool = True,
    include_baskets: bool = False,
) -> list[Target]:
    """Build a live universe: DefiLlama protocols + CoinGecko coin list.

    `include_baskets` unions in every reference-basket token so the screener
    keeps the majors and all five asset classes regardless of TVL churn. A
    basket token already in the top-N keeps its TVL-derived Target (richer
    slug/category), so the union never duplicates a gecko_id.
    """
    cfg = config if config is not None else load_config()
    from dyor.ingestion.coingecko import CoinGeckoClient
    from dyor.ingestion.defillama import DefiLlamaClient

    with DefiLlamaClient(cfg, use_cache=use_cache) as dl:
        protocols = dl.protocols()
    with CoinGeckoClient(cfg, use_cache=use_cache) as cg:
        eth_contracts = eth_contracts_from_coins_list(cg.coins_list())

    targets = targets_from_protocols(protocols, eth_contracts, top_n=top_n, category=category)
    if include_baskets and not category:  # a category filter is a deliberate narrowing
        have = {t.gecko_id for t in targets}
        targets += [t for t in basket_targets(protocols, eth_contracts) if t.gecko_id not in have]
    return targets
