from dyor.universe import (
    DEFAULT_EXCLUDE,
    eth_contracts_from_coins_list,
    targets_from_protocols,
)

PROTOCOLS = [
    {"slug": "uniswap", "gecko_id": "uniswap", "category": "Dexs", "tvl": 5e9},
    {"slug": "aave", "gecko_id": "aave", "category": "Lending", "tvl": 12e9},
    {"slug": "aave-v2", "gecko_id": "aave", "category": "Lending", "tvl": 1e9},  # dupe gecko_id
    {"slug": "okx", "gecko_id": "okb", "category": "CEX", "tvl": 22e9},          # excluded
    {"slug": "no-gecko", "gecko_id": None, "category": "Dexs", "tvl": 9e9},      # no gecko_id
    {"slug": "curve", "gecko_id": "curve-dao-token", "category": "Dexs", "tvl": 2e9},
]

COINS = [
    {"id": "aave", "platforms": {"ethereum": "0x7Fc66500C84A76Ad7e9c93437bFc5Ac33E2DDaE9"}},
    {"id": "uniswap", "platforms": {"ethereum": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984"}},
    {"id": "gmx", "platforms": {"arbitrum-one": "0xfc5..."}},  # no ethereum entry
]


def test_eth_contracts_map_only_ethereum_lowercased():
    m = eth_contracts_from_coins_list(COINS)
    assert m["aave"] == "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9"
    assert "gmx" not in m  # not on ethereum


def test_excludes_cex_and_missing_gecko():
    targets = targets_from_protocols(PROTOCOLS, {}, top_n=10)
    gids = {t.gecko_id for t in targets}
    assert "okb" not in gids          # CEX excluded
    assert all(t.gecko_id for t in targets)  # no gecko_id → dropped
    assert "CEX" in DEFAULT_EXCLUDE


def test_dedupes_gecko_id_keeping_highest_tvl():
    targets = targets_from_protocols(PROTOCOLS, {}, top_n=10)
    aave = [t for t in targets if t.gecko_id == "aave"]
    assert len(aave) == 1
    assert aave[0].defillama_slug == "aave"  # 12e9 wins over aave-v2's 1e9


def test_ranked_by_tvl_and_top_n():
    targets = targets_from_protocols(PROTOCOLS, {}, top_n=2)
    assert [t.gecko_id for t in targets] == ["aave", "uniswap"]  # 12e9, 5e9


def test_auto_resolution_fields():
    targets = targets_from_protocols(PROTOCOLS, eth_contracts_from_coins_list(COINS), top_n=10)
    aave = next(t for t in targets if t.gecko_id == "aave")
    assert aave.defillama_slug == "aave"
    assert aave.santiment_slug == "aave"          # best-effort = gecko_id
    assert aave.cryptorank_key == "aave"
    assert aave.eth_contract == "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9"
    assert aave.category == "Lending"
    curve = next(t for t in targets if t.gecko_id == "curve-dao-token")
    assert curve.eth_contract is None            # not in the coins map


def test_category_filter():
    targets = targets_from_protocols(PROTOCOLS, {}, top_n=10, category="Dexs")
    assert {t.gecko_id for t in targets} == {"uniswap", "curve-dao-token"}


def test_basket_targets_cover_every_class():
    """The screener universe must keep all five asset classes; TVL rank alone
    yields a DeFi-only set."""
    from dyor.classes import REFERENCE_BASKETS
    from dyor.universe import basket_targets

    protos = [{"gecko_id": "aave", "slug": "aave", "category": "Lending", "tvl": 1}]
    targets = basket_targets(protos, {"aave": "0xabc"})
    ids = {t.gecko_id for t in targets}
    expected = {g for ids_ in REFERENCE_BASKETS.values() for g in ids_}
    assert ids == expected
    assert len(targets) == len(expected)          # dogecoin is in two baskets, listed once
    aave = next(t for t in targets if t.gecko_id == "aave")
    assert aave.defillama_slug == "aave" and aave.eth_contract == "0xabc"
    btc = next(t for t in targets if t.gecko_id == "bitcoin")
    assert btc.santiment_slug == "bitcoin" and btc.defillama_slug is None


def test_fetch_universe_union_prefers_tvl_target_and_never_duplicates():
    from dyor.universe import basket_targets, targets_from_protocols

    protos = [
        {"gecko_id": "aave", "slug": "aave", "category": "Lending", "tvl": 100},
        {"gecko_id": "obscure", "slug": "obscure", "category": "Yield", "tvl": 90},
    ]
    tv = targets_from_protocols(protos, {}, top_n=2)
    have = {t.gecko_id for t in tv}
    union = tv + [t for t in basket_targets(protos, {}) if t.gecko_id not in have]
    ids = [t.gecko_id for t in union]
    assert len(ids) == len(set(ids))              # no duplicate gecko_id
    assert ids.count("aave") == 1
    assert "obscure" in ids and "bitcoin" in ids  # TVL entrant and basket major both kept
