"""Universe builder — turn DefiLlama's protocol list into scoring Targets.

Instead of hand-mapping a handful of tokens, build a universe automatically:
take the top-N protocols by TVL (optionally within a category), keep only those
with a CoinGecko `gecko_id` (so market data exists), and **auto-resolve** every
optional id a feed needs. `make_target` is the ONE place that enrichment lives,
so the TVL universe, the reference baskets and on-demand analyze all attach the
same feeds to a token:

  * defillama_slug          — the protocol's own slug (fees/revenue/TVL)
  * chain_name              — DefiLlama chain with this gecko_id (L1 fundamentals:
                              chain-level fees/revenue/TVL when there is no slug)
  * eth_contract            — Ethereum contract (Ethplorer holder concentration)
  * verify_chain_id/address — first contract on a Sourcify-supported chain
  * github_org              — from DefiLlama's `github` list, else caller-supplied
  * audits / has_audit_links— DefiLlama's audit record (the `no_audit` gate)
  * santiment_slug / cryptorank_key — best-effort = gecko_id; the collector
                              upgrades the Santiment slug via `resolve_slug_map`
  * category                — the DefiLlama category, used as the peer group

`targets_from_protocols` and `basket_targets` are pure (data in → Targets out)
so they unit-test on fixtures; `fetch_universe` does the network calls.
"""

from __future__ import annotations

from typing import Any, Iterable

from dyor.collect import Target
from dyor.config import load_config

# Categories that aren't protocol tokens we score the same way.
DEFAULT_EXCLUDE = frozenset({"CEX", "Chain", "Bridge"})

# CoinGecko platform id → EVM chain id, in the order Sourcify is tried. Ethereum
# first (also feeds Ethplorer); the rest cover the common L2/alt-L1 deployments.
VERIFY_CHAINS: list[tuple[str, int]] = [
    ("ethereum", 1), ("arbitrum-one", 42161), ("base", 8453), ("optimistic-ethereum", 10),
    ("polygon-pos", 137), ("binance-smart-chain", 56), ("avalanche", 43114),
]


def eth_contracts_from_coins_list(coins_list: Iterable[dict[str, Any]]) -> dict[str, str]:
    """{gecko_id: lowercased Ethereum contract} from `/coins/list?include_platform`."""
    out: dict[str, str] = {}
    for coin in coins_list:
        addr = (coin.get("platforms") or {}).get("ethereum")
        if coin.get("id") and addr:
            out[coin["id"]] = addr.strip().lower()
    return out


def platforms_from_coins_list(coins_list: Iterable[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """{gecko_id: {platform: lowercased contract}} — every chain, for Sourcify
    and Santiment contract matching."""
    out: dict[str, dict[str, str]] = {}
    for coin in coins_list:
        plats = {k: v.strip().lower() for k, v in (coin.get("platforms") or {}).items() if k and v}
        if coin.get("id") and plats:
            out[coin["id"]] = plats
    return out


def pick_verify_contract(platforms: dict[str, str] | None) -> tuple[int, str] | None:
    """(chain_id, address) of the first deployment on a Sourcify-supported chain."""
    for platform, chain_id in VERIFY_CHAINS:
        addr = (platforms or {}).get(platform)
        if addr:
            return chain_id, addr.lower()
    return None


def chain_index(chains: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """gecko_id → {name, tvl} from DefiLlama `/v2/chains` (highest TVL wins)."""
    out: dict[str, dict[str, Any]] = {}
    for row in chains:
        gid = row.get("gecko_id")
        if not gid or not row.get("name"):
            continue
        tvl = row.get("tvl") or 0
        if gid not in out or tvl > (out[gid].get("tvl") or 0):
            out[gid] = {"name": row["name"], "tvl": tvl}
    return out


def _merge_audits(children: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    """Audit record for a parent from its versions: any link counts; the count is
    the highest any version reports, so "0" survives only when every version
    says "0" (explicit none on record), and None when none reports a count."""
    links: list[str] = []
    counts: list[int] = []
    for k in children:
        for link in k.get("audit_links") or []:
            if link not in links:
                links.append(link)
        a = k.get("audits")
        if a is not None and str(a).strip().isdigit():
            counts.append(int(str(a).strip()))
    return (str(max(counts)) if counts else None), links


def fold_parent_protocols(
    protocols: Iterable[dict[str, Any]], parents: Iterable[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """`protocols` plus one synthetic row per DefiLlama *parent* protocol.

    DefiLlama lists protocol VERSIONS as separate rows (Uniswap V2 / V3 / V4,
    Aave V2 / V3, Curve DEX / LlamaLend …) and their `gecko_id` is usually
    empty — the token's id sits on the parent (`/lite/protocols2` →
    `parentProtocols`). Matching child rows only left Uniswap with no protocol
    at all and gave Aave `aave-v2`, a $113M sliver of a $19B protocol whose
    fees made its P/F 1300× (2026-09-27 audit: 80 → 99 of 135 tokens matched
    once parents count; 19 gained a page, 8 moved from one version to the
    aggregate). The synthetic row: slug = parent slug (its `/summary/fees` and
    `/tvl` serve the aggregate), gecko_id = the parent's or its top version's,
    tvl = Σ versions (so it wins the highest-TVL-per-gecko_id pick), category
    and chains from the top version, audits and github merged, `children` =
    version slugs (the collector's fallback when the parent serves nothing —
    e.g. bonkfun). A parent whose top version is a Chain / CEX / Bridge is
    skipped: that umbrella is not the token's product (NEAR's is a bridge; L1s
    get chain-level fundamentals instead).
    """
    protocols = list(protocols)
    kids: dict[str, list[dict[str, Any]]] = {}
    for p in protocols:
        if p.get("parentProtocol"):
            kids.setdefault(p["parentProtocol"], []).append(p)
    out = list(protocols)
    for par in parents or []:
        pid = par.get("id") or ""
        children = sorted(kids.get(pid, []), key=lambda k: k.get("tvl") or 0, reverse=True)
        if not children or "#" not in pid:
            continue
        gecko = par.get("gecko_id") or next((k["gecko_id"] for k in children if k.get("gecko_id")), None)
        if not gecko:
            continue
        category = children[0].get("category")
        if category in DEFAULT_EXCLUDE:
            continue
        audits, links = _merge_audits(children)
        github: list[str] = []
        for k in children:
            for org in k.get("github") or []:
                if org not in github:
                    github.append(org)
        out.append({
            "slug": pid.split("#", 1)[1],
            "name": par.get("name"),
            "gecko_id": gecko,
            "cmcId": par.get("cmcId"),
            "category": category,
            "chains": par.get("chains") or children[0].get("chains"),
            "tvl": sum((k.get("tvl") or 0) for k in children),
            "audits": audits,
            "audit_links": links,
            "github": github,
            "parentProtocol": None,
            "children": [k["slug"] for k in children],
        })
    return out


def best_by_gecko(protocols: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """gecko_id → the protocol row with the highest TVL (a folded parent's TVL
    is the sum of its versions, so the aggregate beats any single version)."""
    best: dict[str, dict[str, Any]] = {}
    for p in protocols:
        gid = p.get("gecko_id")
        if not gid:
            continue
        if gid not in best or (p.get("tvl") or 0) > (best[gid].get("tvl") or 0):
            best[gid] = p
    return best


def make_target(
    gecko_id: str,
    *,
    dl_info: dict[str, Any] | None = None,
    platforms: dict[str, str] | None = None,
    chain: dict[str, Any] | None = None,
    github_org: str | None = None,
    category: str | None = None,
) -> Target:
    """Attach every resolvable feed id to a token. `dl_info` is a DefiLlama
    protocol row (slug/category/github/audits/audit_links); `chain` is the
    `chain_index` entry; `platforms` is CoinGecko's platform→contract map."""
    info = dl_info or {}
    # A token that IS a chain can also match a Bridge / CEX / Chain "protocol"
    # row by gecko_id (starknet → starknet-bridge, mantle → mantle-bridge). The
    # bridge's TVL and fees are not the token's product; when DefiLlama knows the
    # chain, the chain-level fundamentals are, so the row's slug is dropped.
    if chain and info.get("category") in DEFAULT_EXCLUDE:
        info = {k: v for k, v in info.items() if k != "slug"}
    plats = platforms or {}
    verify = pick_verify_contract(plats)
    dl_github = info.get("github") or []
    # DefiLlama lists chains/CEXs/bridges as "protocols" with audits "0". An
    # audit is only a meaningful expectation of an application protocol — an
    # L1's chain row carrying "0" must not become a no_audit flag on ETH or BTC.
    audit_row = info.get("category") not in DEFAULT_EXCLUDE
    children = info.get("children") or []
    return Target(
        gecko_id=gecko_id,
        defillama_slug=info.get("slug"),
        defillama_fallback_slug=children[0] if children else None,
        github_org=github_org or (dl_github[0] if dl_github else None),
        santiment_slug=gecko_id,
        cryptorank_key=gecko_id,
        eth_contract=plats.get("ethereum"),
        category=category if category is not None else info.get("category"),
        chain_name=(chain or {}).get("name"),
        verify_chain_id=verify[0] if verify else None,
        verify_address=verify[1] if verify else None,
        audits=(str(info["audits"]) if audit_row and info.get("audits") is not None else None),
        has_audit_links=bool(info.get("audit_links")) if audit_row else False,
    )


def targets_from_protocols(
    protocols: Iterable[dict[str, Any]],
    eth_contracts: dict[str, str] | None = None,
    *,
    top_n: int = 50,
    category: str | None = None,
    exclude_categories: frozenset[str] = DEFAULT_EXCLUDE,
    platforms: dict[str, dict[str, str]] | None = None,
    chains: dict[str, dict[str, Any]] | None = None,
) -> list[Target]:
    """Top-N protocols by TVL → fully-resolved Targets.

    Keeps only protocols with a `gecko_id`; optionally restricts to one category.
    De-dupes by gecko_id (a token can run several protocols) keeping highest TVL.
    `eth_contracts` is accepted for back-compat; `platforms` supersedes it.
    """
    plat_map = dict(platforms or {})
    for gid, addr in (eth_contracts or {}).items():
        plat_map.setdefault(gid, {}).setdefault("ethereum", addr)
    chains = chains or {}

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
        make_target(p["gecko_id"], dl_info=p, platforms=plat_map.get(p["gecko_id"]),
                    chain=chains.get(p["gecko_id"]))
        for p in ranked
    ]


def basket_targets(
    protocols: Iterable[dict[str, Any]],
    eth_contracts: dict[str, str] | None = None,
    *,
    classes: Iterable[str] | None = None,
    platforms: dict[str, dict[str, str]] | None = None,
    chains: dict[str, dict[str, Any]] | None = None,
) -> list[Target]:
    """Targets for every token in the class reference baskets (pure).

    TVL rank alone yields a DeFi-only universe that churns week to week — a
    2026-08-24 refresh dropped ethereum, chainlink and celestia and left one L1
    and no memecoins. Pinning the baskets in keeps the majors and every asset
    class present, and makes the screener's composition stable across runs.
    """
    from dyor.classes import REFERENCE_BASKETS

    plat_map = dict(platforms or {})
    for gid, addr in (eth_contracts or {}).items():
        plat_map.setdefault(gid, {}).setdefault("ethereum", addr)
    chains = chains or {}
    by_gecko = best_by_gecko(protocols)  # the aggregate parent beats any single version
    wanted = list(classes) if classes is not None else list(REFERENCE_BASKETS)

    seen: dict[str, Target] = {}
    for cls in wanted:
        for gid in REFERENCE_BASKETS.get(cls, []):
            if gid in seen:
                continue
            seen[gid] = make_target(gid, dl_info=by_gecko.get(gid), platforms=plat_map.get(gid),
                                    chain=chains.get(gid))
    return list(seen.values())


def fetch_identity_maps(config: dict | None = None, *, use_cache: bool = True):
    """(protocols, platforms_by_gecko_id, chain_index) — the three cached calls
    every universe/basket/analyze build needs."""
    cfg = config if config is not None else load_config()
    from dyor.ingestion.coingecko import CoinGeckoClient
    from dyor.ingestion.defillama import DefiLlamaClient

    with DefiLlamaClient(cfg, use_cache=use_cache) as dl:
        protocols = fold_parent_protocols(dl.protocols(), _parents_or_empty(dl))
        chains = chain_index(dl.chains())
    with CoinGeckoClient(cfg, use_cache=use_cache) as cg:
        platforms = platforms_from_coins_list(cg.coins_list())
    return protocols, platforms, chains


def _parents_or_empty(dl) -> list[dict[str, Any]]:
    """The parent list is an enrichment: if the lite endpoint is down, build
    from version rows alone rather than fail the whole universe."""
    try:
        return dl.parent_protocols()
    except Exception:
        return []


def fetch_universe(
    config: dict | None = None,
    *,
    top_n: int = 50,
    category: str | None = None,
    use_cache: bool = True,
    include_baskets: bool = False,
) -> list[Target]:
    """Build a live universe: DefiLlama protocols + chains + CoinGecko coin list.

    `include_baskets` unions in every reference-basket token so the screener
    keeps the majors and all five asset classes regardless of TVL churn. A
    basket token already in the top-N keeps its TVL-derived Target (richer
    slug/category), so the union never duplicates a gecko_id.
    """
    cfg = config if config is not None else load_config()
    protocols, platforms, chains = fetch_identity_maps(cfg, use_cache=use_cache)

    targets = targets_from_protocols(protocols, top_n=top_n, category=category,
                                     platforms=platforms, chains=chains)
    if include_baskets and not category:  # a category filter is a deliberate narrowing
        have = {t.gecko_id for t in targets}
        targets += [t for t in basket_targets(protocols, platforms=platforms, chains=chains)
                    if t.gecko_id not in have]
    return targets
