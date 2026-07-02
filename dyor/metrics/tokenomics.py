"""Tokenomics overhang metrics.

The key insight: an unlock's danger is relative to what the market can absorb.
A $X unlock into thin daily volume is far riskier than the same unlock into deep
liquidity — so `unlock_pct_of_volume` matters more than the raw dollar figure.
"""

from __future__ import annotations

Number = float | int | None


def _safe_div(num: Number, den: Number) -> float | None:
    if num is None or den is None or den <= 0:
        return None
    return num / den


def unlock_pct_of_supply(unlock_amount: Number, circulating_supply: Number) -> float | None:
    """Upcoming unlock as a fraction of circulating supply (×100 for %)."""
    return _safe_div(unlock_amount, circulating_supply)


def unlock_pct_of_volume(unlock_value_usd: Number, avg_daily_volume_usd: Number) -> float | None:
    """Absorption capacity: unlock $ value ÷ average daily volume.

    >1 means the unlock exceeds a full day of volume — high sell-pressure risk.
    """
    return _safe_div(unlock_value_usd, avg_daily_volume_usd)


def float_ratio(circulating_supply: Number, total_supply: Number) -> float | None:
    """Circulating ÷ total. Low float + high FDV = classic overhang setup."""
    return _safe_div(circulating_supply, total_supply)


def inflation_rate(new_supply_annual: Number, circulating_supply: Number) -> float | None:
    """Annualized new supply as a fraction of circulating supply."""
    return _safe_div(new_supply_annual, circulating_supply)


def insider_share(insider_unlock: Number, total_unlock: Number) -> float | None:
    """Insider portion of an upcoming unlock (Tokenomist labels insider vs not)."""
    return _safe_div(insider_unlock, total_unlock)


def unlock_overhang(
    available_supply: Number, max_supply: Number, has_vesting: bool | None
) -> float | None:
    """Fraction of max supply still locked behind a vesting schedule, in [0, 1].

    The "supply glut" risk: tokens contractually scheduled to hit the market.
    Counted only when `has_vesting` is true — structurally-uncreated supply (e.g.
    un-mined BTC) is NOT a pending-dump overhang, so it returns 0.0 there. This
    is the open-data proxy for unlock pressure (CryptoRank v0), distinct from a
    raw float ratio which conflates vesting locks with uncreated supply.

    Lower is better. Returns None if supply data is missing.
    """
    if has_vesting is False:
        return 0.0
    if available_supply is None or not max_supply or max_supply <= 0:
        return None
    locked = 1.0 - (available_supply / max_supply)
    return max(0.0, min(locked, 1.0))


def value_accrual(holders_revenue: Number, revenue: Number) -> float | None:
    """Token-sink strength: fraction of protocol revenue that reaches token
    holders (buyback / burn / staking), in [0, 1].

    The "hard-coded buyback" signal from the thesis: a protocol can earn a lot
    (high revenue) yet pass little to the token (low accrual → weak sink), or
    route most of it back (high accrual → strong sink, e.g. Hyperliquid). Clamped
    to 1.0 since reported holders-revenue can momentarily exceed booked revenue.
    """
    ratio = _safe_div(holders_revenue, revenue)
    if ratio is None:
        return None
    return min(ratio, 1.0)
