"""Minimal JSON schemas for the external fields the code depends on.

These guard against silent API shape drift (the `[]`-vs-dict class of bug):
they assert only the fields the collector/metrics actually read, with their
types, so a renamed or retyped field fails loudly on the next re-record rather
than producing wrong scores. Validated against cassette-replayed responses in
the integration tests.
"""

NUM_OR_NULL = {"type": ["number", "null"]}
STR_OR_NULL = {"type": ["string", "null"]}

# DefiLlama /protocols entry — the cross-source join keys + TVL.
DEFILLAMA_PROTOCOL = {
    "type": "object",
    "required": ["slug"],
    "properties": {
        "slug": {"type": "string"},
        "gecko_id": STR_OR_NULL,
        "cmcId": {"type": ["string", "number", "null"]},
        "tvl": NUM_OR_NULL,
    },
}

# CoinGecko /coins/markets entry — the market fields metrics read.
COINGECKO_MARKET = {
    "type": "object",
    "required": ["id", "market_cap", "total_volume"],
    "properties": {
        "id": {"type": "string"},
        "market_cap": NUM_OR_NULL,
        "fully_diluted_valuation": NUM_OR_NULL,
        "circulating_supply": NUM_OR_NULL,
        "total_supply": NUM_OR_NULL,
        "total_volume": NUM_OR_NULL,
        "ath_change_percentage": NUM_OR_NULL,
    },
}

# CryptoRank v0 coin detail — the supply + vesting fields for unlock overhang.
CRYPTORANK_COIN = {
    "type": "object",
    "required": ["availableSupply", "maxSupply", "hasVesting"],
    "properties": {
        "availableSupply": NUM_OR_NULL,
        "maxSupply": NUM_OR_NULL,
        "hasVesting": {"type": "boolean"},
    },
}

# Ethplorer top-holder entry — address + share (% of supply).
ETHPLORER_HOLDER = {
    "type": "object",
    "required": ["address", "share"],
    "properties": {
        "address": {"type": "string"},
        "share": {"type": "number"},
        "balance": {"type": "number"},
    },
}
