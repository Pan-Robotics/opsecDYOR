"""Valuation metrics, as defined by Token Terminal / DefiLlama.

All functions return `None` on missing inputs or a non-positive denominator,
rather than raising or returning inf — so a missing feed propagates as "unknown"
through to scoring instead of poisoning a weighted sum.

DefiLlama's fee taxonomy matters here:
  Fees            — total paid by users
  Revenue         — subset the protocol keeps (take rate)   (Fees ≥ Revenue)
  Holders Revenue — subset distributed to token holders (buyback/burn/stake)
  Earnings        — Revenue minus token incentives
"""

from __future__ import annotations

Number = float | int | None


def _safe_div(num: Number, den: Number) -> float | None:
    if num is None or den is None:
        return None
    if den <= 0:
        return None
    return num / den


def price_to_fees(market_cap: Number, annualized_fees: Number) -> float | None:
    """P/F = Market Cap ÷ Annualized Fees. Lower = cheaper per $ of user activity.

    Example: $1B mcap / $100M fees → 10.
    """
    return _safe_div(market_cap, annualized_fees)


def price_to_sales(market_cap: Number, annualized_revenue: Number) -> float | None:
    """P/S = Market Cap ÷ Annualized Revenue (fees the protocol retains)."""
    return _safe_div(market_cap, annualized_revenue)


def mc_tvl(market_cap: Number, tvl: Number) -> float | None:
    """MC/TVL. Heuristic: <1 potentially undervalued, >5 potentially rich.
    Compare within category; beware incentive-inflated/transient TVL."""
    return _safe_div(market_cap, tvl)


def fdv(price: Number, total_supply: Number) -> float | None:
    """Fully Diluted Valuation = price × total (or max) supply."""
    if price is None or total_supply is None:
        return None
    return price * total_supply


def market_cap(price: Number, circulating_supply: Number) -> float | None:
    if price is None or circulating_supply is None:
        return None
    return price * circulating_supply


def fdv_mcap_ratio(total_supply: Number, circulating_supply: Number) -> float | None:
    """FDV/MCAP = total ÷ circulating supply. High = large dilution overhang."""
    return _safe_div(total_supply, circulating_supply)


def outstanding_fdv(
    price: Number, total_supply: Number, unallocated_treasury: Number = 0
) -> float | None:
    """DefiLlama 'Outstanding FDV' = price × (total − unallocated treasury).

    More conservative than raw FDV: excludes supply earmarked but not yet in
    circulation or committed.
    """
    if price is None or total_supply is None:
        return None
    treasury = unallocated_treasury or 0
    return price * (total_supply - treasury)


def real_yield(holders_revenue: Number, market_cap_usd: Number) -> float | None:
    """Holder yield funded by actual fees/revenue (not emissions), as a fraction.

    Operationalized from DefiLlama Holders Revenue. Multiply by 100 for APY %.
    Sustainable blue-chip yields ~3–15%; >50% on majors is usually emissions.
    """
    return _safe_div(holders_revenue, market_cap_usd)
