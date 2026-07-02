"""On-chain health metrics: holder concentration and trend signals.

Concentration is computed from a list of holder balances (already de-duplicated
per address). Trend helpers operate on a time-ordered series and report
direction, not level — per the practitioner guidance ("trend, not level").
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

Number = float | int


def _clean(balances: Sequence[Number]) -> np.ndarray:
    arr = np.asarray([b for b in balances if b is not None], dtype="float64")
    return arr[~np.isnan(arr)]


def top_n_concentration(balances: Sequence[Number], n: int = 10) -> float | None:
    """Share of total supply held by the top-N addresses, in [0, 1].

    Lower is healthier — this is a "lower is better" input to normalization.
    """
    arr = _clean(balances)
    total = arr.sum()
    if arr.size == 0 or total <= 0:
        return None
    top = np.sort(arr)[::-1][:n].sum()
    return float(top / total)


def gini(balances: Sequence[Number]) -> float | None:
    """Gini coefficient of holder balances, [0, 1]. 0 = perfectly equal."""
    arr = np.sort(_clean(balances))
    n = arr.size
    if n == 0:
        return None
    total = arr.sum()
    if total <= 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * arr) - (n + 1) * total) / (n * total))


def nakamoto_coefficient(balances: Sequence[Number], threshold: float = 0.51) -> int | None:
    """Minimum number of top holders that together exceed `threshold` of supply.

    Higher = more decentralized. With threshold 0.51 it's the count needed to
    collude for majority control.
    """
    arr = np.sort(_clean(balances))[::-1]
    total = arr.sum()
    if arr.size == 0 or total <= 0:
        return None
    cumulative = np.cumsum(arr) / total
    return int(np.searchsorted(cumulative, threshold) + 1)


def trend_slope(series: Sequence[Number]) -> float | None:
    """Sign-bearing slope of a time-ordered series via least squares.

    Positive = rising (e.g. active-address growth, or — for exchange reserves —
    declining reserves means a *negative* slope = accumulation).
    """
    arr = _clean(series)
    if arr.size < 2:
        return None
    x = np.arange(arr.size, dtype="float64")
    slope, _ = np.polyfit(x, arr, 1)
    return float(slope)


def series_growth(series: Sequence[Number], window_frac: float = 1 / 3) -> float | None:
    """Scale-free relative growth: (mean of last window − mean of first window)
    ÷ |mean of first window|.

    Used for active-address and dev-activity growth — a fraction comparable
    across assets of very different absolute levels (unlike a raw slope). Robust
    to day-to-day spikiness because it averages the head and tail windows.
    Returns None if there's too little data or the baseline is zero.
    """
    arr = _clean(series)
    n = arr.size
    if n < 3:
        return None
    k = max(1, round(n * window_frac))
    early = arr[:k].mean()
    late = arr[-k:].mean()
    if early == 0:
        return None
    return float((late - early) / abs(early))
