"""Data-source coverage work (2026-09-26): every token should get as many feeds
as free data allows, and nothing a supplier returns should be dropped silently."""

from __future__ import annotations

from dyor.collect import (
    audited_from_defillama, build_record, github_org_from_repos,
)
from dyor.ingestion.santiment import resolve_slug_map
from dyor.universe import (
    basket_targets, chain_index, make_target, pick_verify_contract,
    platforms_from_coins_list, targets_from_protocols,
)

MARKET = {"id": "x", "market_cap": 1e9, "circulating_supply": 1e6, "total_supply": 1e6,
          "max_supply": 1e6, "total_volume": 1e7, "current_price": 1000.0,
          "ath_change_percentage": -10.0, "fully_diluted_valuation": 1e9}


# --- CoinGecko meta ------------------------------------------------------------

def test_coin_meta_extracts_tvl_watchlist_and_repos(sample_config, monkeypatch):
    from dyor.ingestion.coingecko import CoinGeckoClient

    cg = CoinGeckoClient(sample_config)
    seen = {}
    def fake(url, params=None):
        seen["params"] = params
        return {"sentiment_votes_up_percentage": 88.0, "categories": ["Lending", None],
                "watchlist_portfolio_users": 252954,
                "market_data": {"total_value_locked": {"usd": 19307015816, "btc": 1},
                                "max_supply_infinite": False},
                "links": {"repos_url": {"github": ["https://github.com/aave/aave-protocol"], "bitbucket": []}}}
    monkeypatch.setattr(cg, "get_json", fake)
    m = cg.coin_meta("aave"); cg.close()
    assert seen["params"]["market_data"] == "true"
    assert seen["params"]["developer_data"] == "false"      # null on the free tier — don't ask
    assert m == {"sentiment": 88.0, "categories": ["Lending"], "tvl_usd": 19307015816,
                 "watchlist_users": 252954, "max_supply_infinite": False,
                 "github_repos": ["https://github.com/aave/aave-protocol"]}


def test_github_org_from_repos():
    assert github_org_from_repos(["https://github.com/aave/aave-protocol"]) == "aave"
    assert github_org_from_repos(["https://github.com/bitcoin/bitcoin/"]) == "bitcoin"
    assert github_org_from_repos([]) is None and github_org_from_repos(None) is None
    assert github_org_from_repos(["https://gitlab.com/x/y"]) is None


def test_github_accounts_checks_every_source_with_overrides_first():
    from dyor.collect import GITHUB_ACCOUNT_OVERRIDES, MAX_GITHUB_ACCOUNTS, github_accounts

    # NEAR: CoinGecko lists the dead `nearprotocol` before the live `near` —
    # every repo's account is a candidate, in order, de-duplicated
    near = ["https://github.com/nearprotocol/nearcore", "https://github.com/near",
            "https://github.com/nearprotocol/near-wallet"]
    assert github_accounts("near", None, near) == ["nearprotocol", "near"]
    # configured / DefiLlama org first; case-insensitive de-dupe against repo URLs
    assert github_accounts("x", "Aave", ["https://github.com/aave/aave-v3-core"]) == ["Aave"]
    # a verified canonical account is checked before whatever CoinGecko still lists
    assert github_accounts("solana", None, ["https://github.com/solana-labs/solana"]) \
        == GITHUB_ACCOUNT_OVERRIDES["solana"] + ["solana-labs"]
    assert github_accounts("nobody", None, None) == []
    assert len(github_accounts("x", None, [f"https://github.com/org{i}/r" for i in range(10)])) == MAX_GITHUB_ACCOUNTS


def test_build_record_carries_dev_activity_events_for_the_gate():
    from dyor.classes import FEATURE_DIRECTION

    assert build_record("aave", MARKET, dev_activity_events=622.0)["dev_activity_events"] == 622.0
    assert build_record("aave", MARKET)["dev_activity_events"] is None
    assert "dev_activity_events" not in FEATURE_DIRECTION  # gate input, never scored


# --- DefiLlama: chain index + audits ------------------------------------------

def test_chain_index_by_gecko_id_highest_tvl_wins():
    idx = chain_index([{"name": "Ethereum", "gecko_id": "ethereum", "tvl": 5e10},
                       {"name": "Ethereum Classic", "gecko_id": "ethereum-classic", "tvl": 1e7},
                       {"name": "Dup", "gecko_id": "ethereum", "tvl": 1},
                       {"name": "NoGid", "tvl": 9}])
    assert idx["ethereum"] == {"name": "Ethereum", "tvl": 5e10}
    assert "NoGid" not in idx and len(idx) == 2


def test_audited_from_defillama_never_infers_a_negative_from_absence():
    assert audited_from_defillama("2", False) is True
    assert audited_from_defillama("0", False) is False        # explicit "none on record"
    assert audited_from_defillama("0", True) is True          # links contradict the count → trust links
    assert audited_from_defillama(None, False) is None        # absent field → unknown
    assert audited_from_defillama("n/a", False) is None


def test_build_record_carries_watchlist_and_audited():
    rec = build_record("x", MARKET, watchlist_users=12345, audited=False)
    assert rec["watchlist_users"] == 12345 and rec["audited"] is False
    rec = build_record("x", MARKET)
    assert rec["watchlist_users"] is None and rec["audited"] is None


# --- Sourcify multi-chain -----------------------------------------------------

def test_pick_verify_contract_prefers_ethereum_then_supported_l2s():
    assert pick_verify_contract({"ethereum": "0xAAA", "base": "0xBBB"}) == (1, "0xaaa")
    assert pick_verify_contract({"solana": "So1", "arbitrum-one": "0xCCC"}) == (42161, "0xccc")
    assert pick_verify_contract({"solana": "So1"}) is None
    assert pick_verify_contract(None) is None


# --- make_target: one enrichment for universe, baskets and analyze ------------

def test_make_target_attaches_every_free_feed_id():
    t = make_target("gmx", dl_info={"slug": "gmx", "category": "Derivatives", "github": ["gmx-io"],
                                    "audits": "2", "audit_links": ["https://a"]},
                    platforms={"arbitrum-one": "0xFC5A1A6EB076a2C7aD06eD22C90d7E710E35ad0a"},
                    chain=None)
    assert t.defillama_slug == "gmx" and t.github_org == "gmx-io" and t.category == "Derivatives"
    assert t.eth_contract is None
    assert (t.verify_chain_id, t.verify_address) == (42161, "0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a")
    assert t.audits == "2" and t.has_audit_links is True
    e = make_target("ethereum", dl_info=None, platforms=None, chain={"name": "Ethereum", "tvl": 5e10})
    assert e.chain_name == "Ethereum" and e.defillama_slug is None and e.audits is None


def test_targets_from_protocols_and_baskets_share_enrichment():
    protos = [{"gecko_id": "aave", "slug": "aave", "category": "Lending", "tvl": 100,
               "github": ["aave"], "audits": "2"},
              {"gecko_id": "cexcoin", "slug": "cex", "category": "CEX", "tvl": 999}]
    plats = platforms_from_coins_list([{"id": "aave", "platforms": {"ethereum": "0xAbC", "base": "0xdef"}},
                                       {"id": "bitcoin", "platforms": {}}])
    chains = {"ethereum": {"name": "Ethereum", "tvl": 1}}
    tv = targets_from_protocols(protos, top_n=5, platforms=plats, chains=chains)
    assert [t.gecko_id for t in tv] == ["aave"]                      # CEX excluded
    assert tv[0].eth_contract == "0xabc" and tv[0].verify_chain_id == 1 and tv[0].github_org == "aave"
    bk = {t.gecko_id: t for t in basket_targets(protos, platforms=plats, chains=chains)}
    assert bk["ethereum"].chain_name == "Ethereum"                    # L1 gets chain-level feeds
    assert bk["aave"].audits == "2"                                   # basket rows share the enrichment


# --- Santiment slug map --------------------------------------------------------

def test_resolve_slug_map_precedence_and_ambiguity():
    projects = [
        {"slug": "aave", "ticker": "AAVE", "name": "Aave", "mainContractAddress": "0xAAA"},
        {"slug": "polkadot-new", "ticker": "DOT", "name": "Polkadot", "mainContractAddress": None},
        {"slug": "some-wrapped", "ticker": "WBTC", "name": "Wrapped BTC", "mainContractAddress": "0xBBB"},
        {"slug": "gigglecoin", "ticker": "GIG", "name": "Giggle", "mainContractAddress": None},
        {"slug": "pepe-a", "ticker": "PEPE", "name": "Pepe A", "mainContractAddress": None},
        {"slug": "pepe-b", "ticker": "PEPE", "name": "Pepe B", "mainContractAddress": None},
    ]
    coins = {"aave": {"name": "Aave", "symbol": "aave", "platforms": {"ethereum": "0xaaa"}},
             "polkadot": {"name": "Polkadot", "symbol": "dot", "platforms": {}},
             "wrapped-bitcoin": {"name": "Wrapped Bitcoin", "symbol": "wbtc", "platforms": {"ethereum": "0xBBB"}},
             "giggle-fund": {"name": "Giggle", "symbol": "gig", "platforms": {}},
             "pepe": {"name": "Pepe", "symbol": "pepe", "platforms": {}},
             "unknown-x": {"name": "Unknown", "symbol": "unk", "platforms": {}}}
    m = resolve_slug_map(projects, coins, list(coins))
    assert m["aave"] == "aave"                    # slug == gecko_id
    assert m["polkadot"] == "polkadot-new"        # override
    assert m["wrapped-bitcoin"] == "some-wrapped" # contract match (case-insensitive)
    assert m["giggle-fund"] == "gigglecoin"       # exact name
    assert "pepe" not in m                        # ambiguous ticker → unresolved, not guessed
    assert "unknown-x" not in m


def test_audits_are_ignored_for_chain_cex_bridge_rows():
    """DefiLlama's chain rows carry audits "0"; that must not flag ETH/BTC/SOL as
    unaudited (it did, in the first production run of this feature)."""
    eth = make_target("ethereum", dl_info={"slug": "ethereum", "category": "Chain", "audits": "0"},
                      chain={"name": "Ethereum", "tvl": 5e10})
    assert eth.audits is None and eth.has_audit_links is False
    app = make_target("babylon", dl_info={"slug": "babylon", "category": "Restaking", "audits": "0"})
    assert app.audits == "0"


def test_audited_only_set_for_defi_classes():
    """The gate is an application-protocol expectation: the same DefiLlama "0"
    yields False for a DeFi record and None for every other class."""
    from dyor.collect import audited_for_class

    assert audited_for_class("defi", "0", False) is False
    assert audited_for_class("general", "0", False) is False
    assert audited_for_class("defi", "2", False) is True
    for cls in ("l1", "monetary", "meme", "stablecoin", None):
        assert audited_for_class(cls, "0", False) is None, cls
        assert audited_for_class(cls, "2", True) is None, cls
