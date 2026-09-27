"""Normalization — the cardinal rule: normalize before combining, otherwise the
largest-magnitude factor dominates.

All functions take an array-like of raw values and return a numpy array of the
same length scaled to roughly [0, 1] (z-score excepted), with NaNs preserved.
`higher_is_better=False` inverts the scale for "lower is better" metrics such as
P/F, FDV/MCAP, or holder concentration.

Percentile rank is preferred (scale-invariant, outlier-robust, interpretable).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

ArrayLike = Sequence[float] | np.ndarray | pd.Series


def percentile_rank(values: ArrayLike, higher_is_better: bool = True) -> np.ndarray:
    """Rank to [0, 1]. Ties share the average rank. NaNs stay NaN.

    Preferred normalizer: scale-invariant and outlier-robust, so a single whale
    balance or one absurd FDV doesn't crush everything else toward zero.
    """
    s = pd.Series(np.asarray(values, dtype="float64"))
    pct = s.rank(pct=True, method="average")
    if not higher_is_better:
        pct = 1.0 - pct
    return pct.to_numpy()


def percentile_of_score(
    value: float | None, reference: ArrayLike, higher_is_better: bool = True
) -> float:
    """Rank ONE value against a *fixed* reference distribution → [0, 1].

    Unlike `percentile_rank` (which ranks a column against itself), this ranks a
    single token's raw value against a frozen per-class reference basket, so the
    result depends only on (value, reference) — not on whatever else is being
    scored in the same batch. That's what makes a token's tier reproducible
    across the analyze subject, a peer table, and the screener.

    Linear interpolation of the empirical CDF: the sorted reference values sit
    at positions 0, 1/(N−1), …, 1 (tied values share their mean position) and
    the token's value is interpolated between its two neighbours; below the
    minimum → 0, above the maximum → 1. Equal to the worst peer scores 0, equal
    to the best scores 1, and — the point — a small move in the value is a
    small move in the percentile. The step convention used before
    ((#below + ½·#equal) / N) turned a 7-token basket into a staircase:
    Bitcoin's float ratio flickering between 0.99998 and 1.0 (CoinGecko
    rounding) crossed three peers sitting at exactly 1.0 and moved the
    percentile by 50 points with no real change (2026-09-27). Empty reference
    or NaN value → NaN (caller falls back).
    """
    ref = np.sort(np.asarray(reference, dtype="float64"))
    ref = ref[~np.isnan(ref)]
    if value is None or (isinstance(value, float) and np.isnan(value)) or ref.size == 0:
        return float("nan")
    v = float(value)
    if ref.size == 1:
        pct = 0.5 if v == ref[0] else (1.0 if v > ref[0] else 0.0)
    else:
        positions = np.arange(ref.size, dtype="float64") / (ref.size - 1)
        xs, inverse = np.unique(ref, return_inverse=True)      # one knot per distinct value …
        knots = np.zeros(xs.size)
        np.add.at(knots, inverse, positions)
        knots /= np.bincount(inverse)                          # … at the mean position of its ties
        pct = float(np.interp(v, xs, knots))                   # clamps to 0 / 1 outside the range
    return pct if higher_is_better else 1.0 - pct


def zscore(values: ArrayLike, higher_is_better: bool = True) -> np.ndarray:
    """Standardize to mean 0 / std 1. Controls for scale but distorts multimodal
    data — prefer percentile_rank unless inputs are roughly normal."""
    arr = np.asarray(values, dtype="float64")
    mean = np.nanmean(arr)
    std = np.nanstd(arr)
    if std == 0 or np.isnan(std):
        return np.zeros_like(arr)
    z = (arr - mean) / std
    return z if higher_is_better else -z


def minmax(
    values: ArrayLike,
    lo: float | None = None,
    hi: float | None = None,
    higher_is_better: bool = True,
) -> np.ndarray:
    """Scale to [0, 1] against [lo, hi]. Good for bounded inputs.

    Pass fixed `lo`/`hi` reference bounds to keep scores comparable across runs
    (otherwise the min/max drift every refresh and break temporal comparison).
    """
    arr = np.asarray(values, dtype="float64")
    lo = float(np.nanmin(arr)) if lo is None else lo
    hi = float(np.nanmax(arr)) if hi is None else hi
    if hi == lo:
        return np.full(arr.shape, 0.5)
    scaled = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    return scaled if higher_is_better else 1.0 - scaled


def saturating(values: ArrayLike, alpha: float) -> np.ndarray:
    """Diminishing-returns transform `x / (x + alpha)` (set alpha ≈ median).

    Prevents a single runaway factor (e.g. one protocol with 100x everyone's
    fees) from dominating a weighted sum. Expects non-negative input.
    """
    arr = np.asarray(values, dtype="float64")
    if alpha <= 0:
        raise ValueError("alpha must be > 0")
    return arr / (arr + alpha)


NORMALIZERS = {
    "percentile": percentile_rank,
    "zscore": zscore,
    "minmax": minmax,
}


def normalize(values: ArrayLike, method: str = "percentile", **kwargs) -> np.ndarray:
    """Dispatch by name (matches `scoring.normalization` in config.yaml)."""
    try:
        fn = NORMALIZERS[method]
    except KeyError:
        raise ValueError(
            f"unknown normalization '{method}'; choose from {sorted(NORMALIZERS)}"
        ) from None
    return fn(values, **kwargs)
