import numpy as np
import pytest

from dyor.scoring import normalize as norm


def test_percentile_rank_orders_and_bounds():
    out = norm.percentile_rank([10, 20, 30, 40])
    assert np.all((out > 0) & (out <= 1.0))
    assert out[0] < out[-1]  # smallest gets lowest rank


def test_percentile_rank_lower_is_better_inverts():
    hi = norm.percentile_rank([1, 2, 3], higher_is_better=True)
    lo = norm.percentile_rank([1, 2, 3], higher_is_better=False)
    np.testing.assert_allclose(hi + lo, np.ones(3), atol=1e-9)


def test_percentile_rank_preserves_nan():
    out = norm.percentile_rank([1.0, np.nan, 3.0])
    assert np.isnan(out[1])
    assert not np.isnan(out[0]) and not np.isnan(out[2])


def test_minmax_bounds_and_constant():
    np.testing.assert_allclose(norm.minmax([0, 5, 10]), [0.0, 0.5, 1.0])
    # constant input → neutral 0.5 everywhere (no spurious spread)
    np.testing.assert_allclose(norm.minmax([7, 7, 7]), [0.5, 0.5, 0.5])


def test_minmax_fixed_reference_bounds_clip():
    out = norm.minmax([5, 50, 500], lo=0, hi=100)
    assert out[0] == pytest.approx(0.05)
    assert out[-1] == 1.0  # clipped at the fixed upper bound


def test_zscore_mean_zero():
    out = norm.zscore([1, 2, 3, 4, 5])
    assert out.mean() == pytest.approx(0.0, abs=1e-9)


def test_zscore_constant_is_zero():
    np.testing.assert_allclose(norm.zscore([3, 3, 3]), [0, 0, 0])


def test_saturating_monotone_and_bounded():
    out = norm.saturating([0, 1, 10, 1000], alpha=1.0)
    assert out[0] == 0.0
    assert np.all(np.diff(out) > 0)
    assert np.all(out < 1.0)


def test_saturating_rejects_bad_alpha():
    with pytest.raises(ValueError):
        norm.saturating([1, 2], alpha=0)


def test_normalize_dispatch_unknown():
    with pytest.raises(ValueError):
        norm.normalize([1, 2], method="bogus")


# --- percentile_of_score (fixed reference) ---------------------------------

def test_percentile_of_score_bounds_and_midpoint():
    ref = [10, 20, 30, 40]
    assert norm.percentile_of_score(5, ref) == 0.0      # below all
    assert norm.percentile_of_score(50, ref) == 1.0     # above all
    assert norm.percentile_of_score(25, ref) == 0.5     # half below


def test_percentile_of_score_is_independent_of_other_values():
    # The SAME raw value against the SAME reference → same percentile, no matter
    # what else is being scored. This is the property that fixes the flutter.
    ref = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert norm.percentile_of_score(3.5, ref) == norm.percentile_of_score(3.5, ref)
    assert norm.percentile_of_score(3.5, ref) == pytest.approx(0.6)


def test_percentile_of_score_lower_is_better_inverts():
    ref = [1, 2, 3, 4]
    hi = norm.percentile_of_score(2.5, ref, higher_is_better=True)
    lo = norm.percentile_of_score(2.5, ref, higher_is_better=False)
    assert hi + lo == pytest.approx(1.0)


def test_percentile_of_score_empty_or_nan_is_nan():
    assert np.isnan(norm.percentile_of_score(5, []))
    assert np.isnan(norm.percentile_of_score(None, [1, 2, 3]))
    assert np.isnan(norm.percentile_of_score(float("nan"), [1, 2, 3]))
