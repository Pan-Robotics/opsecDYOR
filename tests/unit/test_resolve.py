import pytest

from dyor.analyze import target_from_resolved
from dyor.resolve import ResolvedToken, classify_query, resolve_query

AAVE_ETH = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"
SOL_ADDR = "AavE1kKKnesPw4MuRJmJ9jZs9QzEE8CPxQ3ViczUDfc1"


def test_classify_query():
    assert classify_query(AAVE_ETH) == "address"
    assert classify_query(SOL_ADDR) == "address"
    assert classify_query("AAVE") == "text"
    assert classify_query("Lido DAO") == "text"
    assert classify_query("0x123") == "text"  # too short for EVM


class FakeCG:
    """Stand-in CoinGecko client for offline resolution tests."""

    def __init__(self):
        self.contract_calls = []

    def coin_by_contract(self, platform, address):
        self.contract_calls.append(platform)
        if platform != "ethereum":              # only ethereum has it
            raise RuntimeError("404")
        return {"id": "aave", "symbol": "aave", "name": "Aave",
                "platforms": {"ethereum": AAVE_ETH.lower(), "base": "0xabc"},
                "market_cap_rank": 64}

    def search(self, query):
        return {"coins": [
            {"id": "aave", "symbol": "AAVE", "name": "Aave", "market_cap_rank": 64},
            {"id": "aave-fake", "symbol": "AAVE", "name": "Aave Fake", "market_cap_rank": 9000},
        ]}

    def coin_detail(self, coin_id):
        return {"id": coin_id, "symbol": "aave", "name": "Aave",
                "platforms": {"ethereum": AAVE_ETH.lower()}, "market_cap_rank": 64}


@pytest.fixture
def cg():
    return FakeCG()


def test_resolve_by_address_tries_platforms_until_hit(cg, sample_config):
    r = resolve_query(AAVE_ETH, sample_config, client=cg)
    assert r.gecko_id == "aave" and r.matched_by == "address"
    assert "ethereum" in r.chains and "base" in r.chains
    assert cg.contract_calls[0] == "ethereum"  # ethereum tried first


def test_resolve_solana_address_uses_solana_platform(cg, sample_config):
    cg.coin_by_contract = lambda platform, address: (
        {"id": "aave", "symbol": "aave", "name": "Aave", "platforms": {"solana": address}}
        if platform == "solana" else (_ for _ in ()).throw(RuntimeError("404"))
    )
    r = resolve_query(SOL_ADDR, sample_config, client=cg)
    assert r is not None and r.gecko_id == "aave"


def test_resolve_by_symbol_picks_best_rank(cg, sample_config):
    r = resolve_query("AAVE", sample_config, client=cg)
    assert r.gecko_id == "aave"          # rank 64 beats the rank-9000 impostor
    assert r.matched_by == "symbol"


def test_resolve_prefers_marketcap_over_symbol_collision(sample_config):
    """'bitcoin' must resolve to Bitcoin (name, rank 1), not a memecoin whose
    symbol is 'BITCOIN' (rank ~3000)."""
    class CG:
        def search(self, q):
            return {"coins": [
                {"id": "harrypotter-meme", "symbol": "BITCOIN", "name": "HPOS10I", "market_cap_rank": 3000},
                {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "market_cap_rank": 1},
            ]}

        def coin_detail(self, coin_id):
            return {"id": coin_id, "symbol": "btc", "name": "Bitcoin", "platforms": {}}

    r = resolve_query("bitcoin", sample_config, client=CG())
    assert r.gecko_id == "bitcoin" and r.matched_by == "name"


def test_resolve_falls_back_to_gecko_id(sample_config):
    """A query that is itself a CoinGecko id (search misses) resolves via detail."""
    class CG:
        def search(self, q):
            return {"coins": []}

        def coin_detail(self, coin_id):
            assert coin_id == "usd-coin"
            return {"id": "usd-coin", "symbol": "usdc", "name": "USDC", "platforms": {}}

    r = resolve_query("usd-coin", sample_config, client=CG())
    assert r is not None and r.gecko_id == "usd-coin" and r.matched_by == "id"


def test_resolve_unknown_returns_none(sample_config):
    class Empty:
        def search(self, q):
            return {"coins": []}

        def coin_detail(self, coin_id):
            raise RuntimeError("404")
    assert resolve_query("nonsensetoken", sample_config, client=Empty()) is None


def test_target_from_resolved_auto_resolves_ids():
    resolved = ResolvedToken("aave", "AAVE", "Aave",
                             platforms={"ethereum": AAVE_ETH.lower()}, matched_by="symbol")
    target = target_from_resolved(resolved, {"aave": {"slug": "aave", "category": "Lending"}})
    assert target.defillama_slug == "aave"
    assert target.eth_contract == AAVE_ETH.lower()
    assert target.santiment_slug == "aave" and target.cryptorank_key == "aave"
    assert target.category == "Lending"


def test_target_from_resolved_without_defillama_match():
    resolved = ResolvedToken("chainlink", "LINK", "Chainlink", platforms={"ethereum": "0xabc"})
    target = target_from_resolved(resolved, {})  # not a DeFi protocol
    assert target.defillama_slug is None
    assert target.eth_contract == "0xabc"


def test_explorer_links_built_per_chain():
    rt = ResolvedToken("aave", "AAVE", "Aave",
                       platforms={"ethereum": "0xABC", "base": "0xDEF", "obscurechain": "0x1"})
    links = rt.explorer_links()
    assert links["ethereum"] == "https://etherscan.io/token/0xABC"
    assert links["base"] == "https://basescan.org/token/0xDEF"
    assert "obscurechain" not in links  # no explorer template → skipped
    assert rt.coingecko_url == "https://www.coingecko.com/en/coins/aave"


def test_extract_links_parses_coin_detail():
    from dyor.resolve import _extract_links

    detail = {"links": {
        "homepage": ["https://aave.com", ""],
        "repos_url": {"github": ["https://github.com/aave/aave-v3-core"]},
        "twitter_screen_name": "aave",
        "subreddit_url": "https://www.reddit.com/r/Aave_Official",
        "telegram_channel_identifier": "Aavesome",
        "chat_url": ["https://aave.com/discord"],
        "whitepaper": "https://aave.com/wp.pdf",
        "blockchain_site": ["https://etherscan.io/token/0x..", "", "https://x.io"],
    }}
    out = _extract_links(detail)
    assert out["homepage"] == "https://aave.com"
    assert out["github"].endswith("aave-v3-core")
    assert out["twitter"] == "https://x.com/aave"
    assert out["reddit"].endswith("Aave_Official")
    assert out["telegram"] == "https://t.me/Aavesome"
    assert out["discord"] == "https://aave.com/discord"
    assert out["whitepaper"].endswith("wp.pdf")
    assert len(out["explorers"]) == 2  # empties filtered

    assert _extract_links({})["homepage"] is None  # no links → all None/empty
