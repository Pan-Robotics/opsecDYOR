"""Human-facing copy: feature/domain glossary + tier styling.

Kept separate from the dashboard so the explanatory text (what each metric means,
why it matters, which direction is good) lives in one place and drives both the
tooltips and the Token Detail glossary.
"""

from __future__ import annotations

# feature -> (label, plain-English meaning, "higher" | "lower" is better)
FEATURE_META: dict[str, tuple[str, str, str]] = {
    # fundamental
    "price_to_fees": ("P/F", "Market cap ÷ annualized fees — how expensive the token is per $ of user activity.", "lower"),
    "price_to_sales": ("P/S", "Market cap ÷ annualized revenue the protocol actually keeps.", "lower"),
    "mc_tvl": ("MC / TVL", "Market cap ÷ total value locked. Under 1 looks cheap, over 5 looks rich.", "lower"),
    "real_yield": ("Real yield", "Holder yield funded by real revenue, not token emissions.", "higher"),
    # tokenomics
    "fdv_mcap_ratio": ("FDV / MCAP", "Fully-diluted ÷ circulating value. High means a large dilution overhang.", "lower"),
    "unlock_overhang": ("Unlock overhang", "Share of max supply still locked behind vesting — future sell pressure.", "lower"),
    "unlock_pct_of_volume": ("Unlock ÷ volume", "Next unlock's $ value ÷ daily volume. Can the market absorb it?", "lower"),
    "float_ratio": ("Float", "Circulating ÷ total supply. Low float + high FDV is the classic trap.", "higher"),
    "inflation_rate": ("Inflation", "Annual new supply ÷ circulating supply.", "lower"),
    "value_accrual": ("Token sink", "Share of revenue routed back to holders (buyback / burn / staking).", "higher"),
    # on-chain
    "top10_concentration": ("Top-10 holders", "Supply held by the 10 largest wallets. High = whale / dump risk.", "lower"),
    "address_growth": ("Active-address growth", "Trend in daily active addresses over the last ~month.", "higher"),
    "reserve_trend": ("Exchange reserves", "Trend in exchange-held supply. Declining = accumulation.", "lower"),
    # social
    "social_trend": ("Social trend", "Trend in social volume / mentions (Santiment).", "higher"),
    "social_sentiment": ("Sentiment", "CoinGecko community up-vote share (keyless, coarse).", "higher"),
    # dev
    "dev_commit_trend": ("Dev-activity trend", "Trend in developer activity over the last ~month.", "higher"),
    "days_since_last_commit": ("Days since last push", "How recently the team shipped code (gate input).", "lower"),
}

DOMAIN_META: dict[str, tuple[str, str]] = {
    "fundamental": ("Fundamentals", "Valuation & cash flow — is it cheap relative to real economic activity?"),
    "tokenomics": ("Tokenomics", "Supply structure — dilution, unlocks, float, and value accrual to holders."),
    "onchain": ("On-chain", "Usage & distribution — active-address growth and holder concentration."),
    "social": ("Social", "Attention — is social interest rising ahead of price?"),
    "dev": ("Developers", "Builder activity — is the team still shipping, especially in a downturn?"),
}

# The framework's "break your thesis" stress-test prompts (Video 2).
BREAK_THESIS = [
    "User retention — what happens if users leave? Is liquidity sticky or mercenary?",
    "Supply shifts — what happens at the next unlock? Are early investors incentivized to dump?",
    "Regulation — does it depend on regulatory ambiguity? What if it's deemed a security?",
    "Bear-market survival — can it survive a severe drawdown (alts fall harder than BTC)?",
    "The final question — if everything you just worried about were true, would you still own it?",
]

_TIER_COLOR = {"A": "green", "B": "blue", "C": "orange", "D": "red"}


def tier_color(tier: str) -> str:
    """Streamlit color name for a tier label like 'A — high conviction'."""
    return _TIER_COLOR.get(tier.strip()[:1], "gray")


def tier_badge(tier: str) -> str:
    """Colored-markdown badge, e.g. ':green[A — high conviction]'."""
    return f":{tier_color(tier)}[**{tier}**]"
