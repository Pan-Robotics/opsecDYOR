"""Entity resolution keyed on `chain:address`.

The rule: match on contract+chain, never on ticker/symbol (symbols collide
constantly). CoinGecko `id` is the canonical entity; DefiLlama joins to it via
`gecko_id`. The output is a crosswalk row per `chain:address`.

Functions here are pure (data in → data out) so they unit-test against fixtures
without touching the network or DuckDB. Persisting goes through `store.db`.

Watch-outs encoded here:
  * addresses are lowercased (the primary-key normalization)
  * CoinGecko platform IDs are strings ("polygon-pos"), not numeric chain IDs
  * a coin with no platforms (e.g. native BTC) still gets a row keyed on its id
"""

from __future__ import annotations

from typing import Any, Iterable


def chain_address(chain: str, address: str) -> str:
    """Canonical primary key: 'chain:loweraddress' (DefiLlama-native form)."""
    return f"{chain.strip().lower()}:{address.strip().lower()}"


def crosswalk_from_coingecko(coins_list: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Explode CoinGecko `/coins/list?include_platform=true` into crosswalk rows.

    One row per (coin, platform). Coins with no platform contracts (native
    assets) yield a single row keyed `native:<id>` so they remain joinable.
    """
    rows: list[dict[str, Any]] = []
    for coin in coins_list:
        gecko_id = coin.get("id")
        symbol = coin.get("symbol")
        name = coin.get("name")
        platforms = coin.get("platforms") or {}

        contracts = {c: a for c, a in platforms.items() if c and a}
        if not contracts:
            rows.append({
                "chain_address": chain_address("native", gecko_id or ""),
                "chain": "native",
                "address": gecko_id,
                "gecko_id": gecko_id,
                "defillama_slug": None,
                "cmc_id": None,
                "symbol": symbol,
                "name": name,
            })
            continue

        for chain, address in contracts.items():
            rows.append({
                "chain_address": chain_address(chain, address),
                "chain": chain.strip().lower(),
                "address": address.strip().lower(),
                "gecko_id": gecko_id,
                "defillama_slug": None,
                "cmc_id": None,
                "symbol": symbol,
                "name": name,
            })
    return rows


def index_defillama_by_gecko(protocols: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """gecko_id → {slug, cmcId} from DefiLlama `/protocols`.

    When several protocols share a gecko_id, the highest-TVL one wins (the
    canonical token, not a satellite deployment).
    """
    best: dict[str, dict[str, Any]] = {}
    for proto in protocols:
        gid = proto.get("gecko_id")
        if not gid:
            continue
        tvl = proto.get("tvl") or 0
        if gid not in best or tvl > best[gid]["tvl"]:
            best[gid] = {
                "slug": proto.get("slug"),
                "cmc_id": proto.get("cmcId"),
                "tvl": tvl,
            }
    return best


def join_defillama(
    crosswalk: list[dict[str, Any]],
    protocols: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich crosswalk rows with DefiLlama slug + cmc_id via `gecko_id`."""
    by_gecko = index_defillama_by_gecko(protocols)
    for row in crosswalk:
        match = by_gecko.get(row.get("gecko_id"))
        if match:
            row["defillama_slug"] = match["slug"]
            row["cmc_id"] = match["cmc_id"]
    return crosswalk


def build_crosswalk(
    coins_list: Iterable[dict[str, Any]],
    protocols: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Full pipeline: CoinGecko explode → DefiLlama join. The public entry point."""
    rows = crosswalk_from_coingecko(coins_list)
    return join_defillama(rows, protocols)
