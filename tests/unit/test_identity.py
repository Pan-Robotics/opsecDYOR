from dyor.identity import resolver

COINS = [
    {
        "id": "usd-coin", "symbol": "usdc", "name": "USDC",
        "platforms": {
            "ethereum": "0xA0b86991c6218B36C1D19D4A2E9EB0CE3606EB48",
            "polygon-pos": "0x3c499c542CEF5E3811E1192CE70D8CC03D5C3359",
        },
    },
    {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "platforms": {}},
]

PROTOCOLS = [
    {"slug": "aave", "gecko_id": "aave", "cmcId": "7278", "tvl": 12_000_000_000},
    {"slug": "usdc-bridge", "gecko_id": "usd-coin", "cmcId": "3408", "tvl": 100},
    {"slug": "usdc-main", "gecko_id": "usd-coin", "cmcId": "3408", "tvl": 50_000},
]


def test_chain_address_lowercases():
    assert resolver.chain_address("Ethereum", "0xABC") == "ethereum:0xabc"


def test_crosswalk_explodes_platforms():
    rows = resolver.crosswalk_from_coingecko(COINS)
    keys = {r["chain_address"] for r in rows}
    assert "ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48" in keys
    assert "polygon-pos:0x3c499c542cef5e3811e1192ce70d8cc03d5c3359" in keys
    # native asset with no platforms still gets a joinable row
    assert "native:bitcoin" in keys


def test_native_asset_row_shape():
    rows = resolver.crosswalk_from_coingecko(COINS)
    btc = next(r for r in rows if r["gecko_id"] == "bitcoin")
    assert btc["chain"] == "native"
    assert btc["symbol"] == "btc"


def test_defillama_join_picks_highest_tvl():
    rows = resolver.build_crosswalk(COINS, PROTOCOLS)
    usdc = next(r for r in rows if r["gecko_id"] == "usd-coin")
    # of the two usd-coin protocols, the 50k-TVL one wins over the 100-TVL one
    assert usdc["defillama_slug"] == "usdc-main"
    assert usdc["cmc_id"] == "3408"


def test_unmatched_gecko_id_has_no_slug():
    rows = resolver.build_crosswalk(COINS, PROTOCOLS)
    btc = next(r for r in rows if r["gecko_id"] == "bitcoin")
    assert btc["defillama_slug"] is None
