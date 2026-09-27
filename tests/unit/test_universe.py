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


def test_fold_parent_protocols_gives_versions_their_parent_slug():
    """DefiLlama's version rows carry no gecko_id; the parent does. Uniswap had
    no protocol and Aave had `aave-v2` (2026-09-27 audit)."""
    import pytest

    from dyor.universe import best_by_gecko, fold_parent_protocols, make_target

    protos = [
        {"slug": "uniswap-v3", "gecko_id": None, "parentProtocol": "parent#uniswap", "category": "Dexs",
         "tvl": 1.6e9, "audits": "2", "audit_links": ["a"], "github": ["Uniswap"], "chains": ["Ethereum"]},
        {"slug": "uniswap-v2", "gecko_id": None, "parentProtocol": "parent#uniswap", "category": "Dexs",
         "tvl": 1.0e9, "audits": "0"},
        {"slug": "aave-v3", "gecko_id": None, "parentProtocol": "parent#aave", "category": "Lending",
         "tvl": 18e9, "audits": "3"},
        {"slug": "aave-v2", "gecko_id": "aave", "parentProtocol": "parent#aave", "category": "Lending",
         "tvl": 0.1e9, "audits": "2"},
        {"slug": "rainbow-bridge", "gecko_id": None, "parentProtocol": "parent#near-protocol",
         "category": "Bridge", "tvl": 4e8},
        {"slug": "lido", "gecko_id": "lido-dao", "category": "Liquid Staking", "tvl": 26e9},
    ]
    parents = [
        {"id": "parent#uniswap", "name": "Uniswap", "gecko_id": "uniswap", "chains": ["Ethereum", "Base"]},
        {"id": "parent#aave", "name": "Aave", "gecko_id": None},
        {"id": "parent#near-protocol", "name": "Near Protocol", "gecko_id": "near"},
        {"id": "parent#orphan", "name": "Orphan", "gecko_id": "orphan"},
    ]
    folded = fold_parent_protocols(protos, parents)
    by = {p["slug"]: p for p in folded}
    uni = by["uniswap"]
    assert uni["gecko_id"] == "uniswap" and uni["tvl"] == pytest.approx(2.6e9) and uni["category"] == "Dexs"
    assert uni["children"] == ["uniswap-v3", "uniswap-v2"]
    assert uni["audits"] == "2" and uni["audit_links"] == ["a"] and uni["github"] == ["Uniswap"]
    assert uni["chains"] == ["Ethereum", "Base"]
    aave = by["aave"]                        # parent has no gecko_id: the version's carries over
    assert aave["gecko_id"] == "aave" and aave["tvl"] == pytest.approx(18.1e9) and aave["audits"] == "3"
    assert "near-protocol" not in by         # a Bridge umbrella is not the token's product
    assert "orphan" not in by                # no versions → nothing to aggregate
    assert len(folded) == len(protos) + 2 and by["uniswap-v3"] is protos[0]   # originals untouched
    # every consumer prefers the aggregate over a single version
    idx = best_by_gecko(folded)
    assert idx["aave"]["slug"] == "aave" and idx["uniswap"]["slug"] == "uniswap" and idx["lido-dao"]["slug"] == "lido"
    tv = {t.gecko_id: t for t in targets_from_protocols(folded, {}, top_n=10)}
    assert tv["aave"].defillama_slug == "aave" and tv["aave"].defillama_fallback_slug == "aave-v3"
    assert tv["uniswap"].defillama_slug == "uniswap" and tv["uniswap"].github_org == "Uniswap"
    assert make_target("lido-dao", dl_info=by["lido"]).defillama_fallback_slug is None
    # all versions saying "0" is an explicit none-on-record; a missing count is unknown
    z = fold_parent_protocols([{"slug": "x-v1", "gecko_id": "x", "parentProtocol": "parent#x", "tvl": 1, "audits": "0"},
                               {"slug": "x-v2", "gecko_id": None, "parentProtocol": "parent#x", "tvl": 2, "audits": "0"}],
                              [{"id": "parent#x", "name": "X"}])
    assert {p["slug"]: p.get("audits") for p in z}["x"] == "0"
    n = fold_parent_protocols([{"slug": "y-v1", "gecko_id": "y", "parentProtocol": "parent#y", "tvl": 1}],
                              [{"id": "parent#y", "name": "Y"}])
    assert {p["slug"]: p.get("audits") for p in n}["y"] is None


def test_chain_beats_a_bridge_row_for_a_chain_token():
    from dyor.universe import make_target

    bridge = {"slug": "starknet-bridge", "gecko_id": "starknet", "category": "Bridge", "tvl": 1e9,
              "github": ["starkware-libs"], "audits": "0"}
    t = make_target("starknet", dl_info=bridge, chain={"name": "Starknet", "tvl": 5e8})
    assert t.defillama_slug is None and t.chain_name == "Starknet"      # chain-level fundamentals
    assert t.github_org == "starkware-libs" and t.audits is None        # other enrichment kept
    # without a chain entry the row still serves (better than nothing)
    assert make_target("starknet", dl_info=bridge).defillama_slug == "starknet-bridge"
    # an application protocol is never overridden by a chain of the same id
    app = {"slug": "aave", "gecko_id": "aave", "category": "Lending", "tvl": 1e9}
    assert make_target("aave", dl_info=app, chain={"name": "Aave Chain", "tvl": 1}).defillama_slug == "aave"


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
