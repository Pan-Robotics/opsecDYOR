"""Asset-class-aware scoring profiles.

A token that isn't a cash-flow protocol shouldn't be judged like one. A monetary
asset (BTC), an L1 (ETH/SOL), a memecoin (DOGE), or a stablecoin (USDC) each get
a profile that scores only the dimensions that matter for it — so "no protocol
revenue" is a fatal miss for a DeFi app but a non-issue for Bitcoin.

Each profile defines a `feature_spec` (which domains/features apply) and domain
`weights`. `classify_asset` assigns a class from CoinGecko categories, DefiLlama
category, whether fee data exists, and known-id safety nets.

The `defi`/`general` profile's weights come from `config.yaml` (the existing
default); other classes' weights are defined here.
"""

from __future__ import annotations

from dataclasses import dataclass

# Direction of each feature: True = higher is better, False = lower is better.
# Must be consistent wherever a feature is used.
FEATURE_DIRECTION: dict[str, bool] = {
    "price_to_fees": False, "price_to_sales": False, "mc_tvl": False, "real_yield": True,
    "fdv_mcap_ratio": False, "unlock_overhang": False, "unlock_pct_of_volume": False,
    "float_ratio": True, "inflation_rate": False, "value_accrual": True,
    "top10_concentration": False, "address_growth": True, "reserve_trend": False,
    "social_trend": True, "social_sentiment": True, "dev_commit_trend": True,
}


def _spec(**domains: list[str]) -> dict[str, list[tuple[str, bool]]]:
    """Build a feature_spec from domain → [feature names], attaching directions."""
    return {d: [(f, FEATURE_DIRECTION[f]) for f in feats] for d, feats in domains.items()}


# Per-class feature specs (which features are even *considered* for the class).
FEATURE_SPECS: dict[str, dict[str, list[tuple[str, bool]]]] = {
    # Cash-flow protocols — the original model.
    "defi": _spec(
        fundamental=["price_to_fees", "price_to_sales", "mc_tvl", "real_yield"],
        tokenomics=["fdv_mcap_ratio", "unlock_overhang", "unlock_pct_of_volume",
                    "float_ratio", "inflation_rate", "value_accrual"],
        onchain=["top10_concentration", "address_growth"],
        social=["social_trend", "social_sentiment"],
        dev=["dev_commit_trend"],
    ),
    # Smart-contract platforms — ecosystem TVL + adoption + dev heavy; fees apply
    # but matter less than for a single app.
    "l1": _spec(
        fundamental=["mc_tvl", "price_to_fees", "price_to_sales", "real_yield"],
        tokenomics=["fdv_mcap_ratio", "unlock_overhang", "float_ratio",
                    "inflation_rate", "value_accrual"],
        onchain=["top10_concentration", "address_growth"],
        social=["social_trend", "social_sentiment"],
        dev=["dev_commit_trend"],
    ),
    # Monetary / store-of-value — NO protocol cash flow. Scarcity + decentralized
    # accumulation + adoption.
    "monetary": _spec(
        tokenomics=["inflation_rate", "float_ratio", "fdv_mcap_ratio", "unlock_overhang"],
        onchain=["top10_concentration", "address_growth", "reserve_trend"],
        social=["social_trend", "social_sentiment"],
        dev=["dev_commit_trend"],
    ),
    # Memecoins — distribution + liquidity + attention; no fundamentals, no dev.
    "meme": _spec(
        tokenomics=["float_ratio", "unlock_overhang"],
        onchain=["top10_concentration", "address_growth"],
        social=["social_trend", "social_sentiment"],
    ),
    # Stablecoins — not an appreciation play; scored for adoption + distribution.
    "stablecoin": _spec(
        onchain=["top10_concentration", "address_growth"],
        social=["social_sentiment"],
    ),
}
FEATURE_SPECS["general"] = FEATURE_SPECS["defi"]  # default == defi

# Core domains a class is EXPECTED to have data for. Missing a core domain is a
# penalty (the class is defined by it), not a forgiven data gap. DeFi is defined
# by cash flow, so an app with no measurable fees/revenue/TVL is penalized;
# other classes leave this empty (missing data is a gap, not a value flaw).
REQUIRED_DOMAINS: dict[str, frozenset[str]] = {
    "defi": frozenset({"fundamental"}),
    "general": frozenset({"fundamental"}),
}

# Non-defi class weights (sum to 1.0 each). defi/general come from config.yaml.
STATIC_WEIGHTS: dict[str, dict[str, float]] = {
    "l1": {"fundamental": 0.18, "tokenomics": 0.20, "onchain": 0.25, "social": 0.12, "dev": 0.25},
    "monetary": {"tokenomics": 0.35, "onchain": 0.35, "social": 0.12, "dev": 0.18},
    "meme": {"tokenomics": 0.20, "onchain": 0.35, "social": 0.45},
    "stablecoin": {"onchain": 0.65, "social": 0.35},
}

LABELS: dict[str, tuple[str, str]] = {
    "defi": ("DeFi protocol", "Cash-flow app — judged on fees, revenue, TVL, and value accrual."),
    "general": ("General", "Default profile (DeFi-style) — judged on fundamentals + tokenomics."),
    "l1": ("L1 / platform", "Smart-contract platform — ecosystem TVL, adoption, and dev activity lead."),
    "monetary": ("Monetary / store-of-value", "No protocol revenue expected — judged on scarcity, decentralized accumulation, and adoption."),
    "meme": ("Memecoin", "Speculative — judged on distribution, liquidity, and social attention; not fundamentals."),
    "stablecoin": ("Stablecoin", "Not a price-appreciation play — scored for adoption and holder distribution only."),
}

# Known-id safety nets (categories can be missing/sparse from CoinGecko).
MONETARY_IDS = {"bitcoin", "litecoin", "bitcoin-cash", "monero", "zcash", "dash",
                "bitcoin-cash-sv", "ecash", "digibyte", "dogecoin-2"}
L1_IDS = {"ethereum", "solana", "avalanche-2", "cardano", "polkadot", "near", "aptos",
          "sui", "cosmos", "tron", "binancecoin", "the-open-network", "internet-computer",
          "hedera-hashgraph", "algorand", "tezos", "stellar", "ethereum-classic", "kaspa",
          "sei-network", "injective-protocol", "celestia", "mantle", "fantom", "arbitrum",
          "optimism", "matic-network", "polygon-ecosystem-token"}
STABLE_IDS = {"tether", "usd-coin", "dai", "first-digital-usd", "true-usd", "frax",
              "usdd", "paypal-usd", "ethena-usde", "binance-usd", "usds"}
MEME_IDS = {"dogecoin", "shiba-inu", "pepe", "dogwifcoin", "bonk", "floki",
            "mog-coin", "popcat", "book-of-meme", "brett-based"}


# Curated reference baskets — representative tokens per class, so a token can be
# scored against same-class peers (an L1 vs L1s, not vs DeFi apps). Collected and
# cached by `dyor reference`; used by analyze peer_mode="class".
# The anchor distributions are built from these ONLY (see dyor/reference.py) —
# a wider basket gives smoother percentiles, so defi/l1 are deliberately broad.
# Changing a basket changes every same-class score: rebuild with `dyor reference`.
REFERENCE_BASKETS: dict[str, list[str]] = {
    "l1": ["ethereum", "solana", "avalanche-2", "cardano", "polkadot", "near",
           "aptos", "sui", "tron", "the-open-network", "internet-computer", "sei-network",
           "binancecoin", "cosmos", "celestia"],
    "monetary": ["bitcoin", "litecoin", "bitcoin-cash", "monero", "zcash", "dash", "dogecoin"],
    "meme": ["dogecoin", "shiba-inu", "pepe", "dogwifcoin", "bonk", "floki", "popcat"],
    "defi": ["aave", "uniswap", "lido-dao", "gmx", "curve-dao-token", "maker",
             "compound-governance-token", "pendle", "convex-finance", "rocket-pool",
             "pancakeswap-token", "sushi", "1inch", "balancer", "yearn-finance",
             "synthetix-network-token", "morpho", "aerodrome-finance", "velodrome-finance",
             "raydium", "jupiter-exchange-solana", "ethena", "frax-share",
             "stargate-finance", "jito-governance-token", "dydx-chain"],
    "stablecoin": ["tether", "usd-coin", "dai", "ethena-usde", "first-digital-usd",
                   "true-usd", "frax"],
}


@dataclass(frozen=True)
class ClassProfile:
    name: str
    label: str
    description: str
    feature_spec: dict[str, list[tuple[str, bool]]]
    weights: dict[str, float]
    required_domains: frozenset[str] = frozenset()


def classify_asset(
    *,
    gecko_id: str | None = None,
    coingecko_categories: list[str] | None = None,
    defillama_category: str | None = None,
    has_fees: bool = False,
    price: float | None = None,
) -> str:
    """Assign an asset class. Order matters: most specific first.

    Stablecoin detection excludes "Stablecoin Issuer" (a DeFi protocol like Aave
    that *issues* a stablecoin is not one) and, when a price is known, requires a
    rough peg — so a $75 governance token is never a stablecoin. DeFi (has fees /
    DeFi category) is checked before L1, since DeFi tokens often also carry
    L1-ecosystem tags.
    """
    gid = (gecko_id or "").lower()
    cats = {c.lower() for c in (coingecko_categories or [])}
    is_pegged = price is not None and 0.5 <= price <= 1.5
    is_stable_cat = any("stablecoin" in c and "issuer" not in c for c in cats)

    if gid in STABLE_IDS or (is_stable_cat and (is_pegged or price is None)):
        return "stablecoin"
    if gid in MEME_IDS or "meme" in cats:
        return "meme"
    if gid in MONETARY_IDS or (
        not has_fees and "decentralized finance (defi)" not in cats
        and ("proof of work (pow)" in cats or "privacy coins" in cats)
    ):
        return "monetary"
    # Precise L1 id-set wins over has-fees: ETH/SOL have DefiLlama fee data but
    # are platforms, not DeFi apps.
    if gid in L1_IDS:
        return "l1"
    if has_fees or defillama_category or "decentralized finance (defi)" in cats:
        return "defi"
    # Broad L1-by-category check last (a DeFi app with a stray platform tag stays DeFi).
    if "layer 1 (l1)" in cats or "smart contract platform" in cats:
        return "l1"
    return "general"


def class_profile(name: str | None, config: dict | None = None) -> ClassProfile:
    """Resolve a class name to its profile (defaults to 'general')."""
    key = name if name in FEATURE_SPECS else "general"
    spec = FEATURE_SPECS[key]
    if key in ("defi", "general"):
        from dyor.config import load_config
        cfg = config if config is not None else load_config()
        weights = dict(cfg["scoring"]["weights"])
    else:
        weights = STATIC_WEIGHTS[key]
    label, desc = LABELS[key]
    return ClassProfile(key, label, desc, spec, weights, REQUIRED_DOMAINS.get(key, frozenset()))
