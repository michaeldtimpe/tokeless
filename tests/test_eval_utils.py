"""Tests for tokeless.eval._utils.

The percentile function intentionally implements linear interpolation
manually rather than via statistics.quantiles. These tests pin the
exact numeric behavior so the implementation can be evolved (e.g. if
we ever swap interpolation method) without silent drift.
"""

from tokeless.eval._utils import percentile


def test_percentile_empty_returns_zero():
    """No data → 0.0 sentinel. Caller is expected to either special-case
    or accept the sentinel; the function never raises."""
    assert percentile([], 50) == 0.0
    assert percentile([], 0) == 0.0
    assert percentile([], 100) == 0.0


def test_percentile_single_returns_self():
    """n=1 short-circuit: any percentile returns the single value.
    statistics.quantiles would raise StatisticsError here."""
    assert percentile([42.5], 0) == 42.5
    assert percentile([42.5], 50) == 42.5
    assert percentile([42.5], 95) == 42.5
    assert percentile([42.5], 100) == 42.5


def test_percentile_two_items_p95_stays_in_range():
    """[10, 20] p95: rank = 0.95 * 1 = 0.95, lo=0, hi=1, frac=0.95
    → 10 + 0.95 * (20 - 10) = 19.5. Crucially, this is BELOW 20 — the
    inclusive-linear behavior never extrapolates above max(values).
    statistics.quantiles with default exclusive method yields 28.5
    here, which is the bug we are deliberately avoiding."""
    assert percentile([10.0, 20.0], 95) == 19.5
    assert percentile([10.0, 20.0], 50) == 15.0
    assert percentile([10.0, 20.0], 0) == 10.0
    assert percentile([10.0, 20.0], 100) == 20.0


def test_percentile_five_items_known_answers():
    """[10, 20, 30, 40, 50]:
        p50: rank = 0.5 * 4 = 2.0 → exact index 2 → 30
        p95: rank = 0.95 * 4 = 3.8 → between index 3 (40) and 4 (50),
                                     frac = 0.8 → 40 + 0.8 * 10 = 48
        p25: rank = 0.25 * 4 = 1.0 → exact index 1 → 20
    Hand-derived; matches numpy.percentile([10,20,30,40,50], q,
    method='linear') for q in {50, 95, 25}."""
    xs = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(xs, 50) == 30.0
    assert percentile(xs, 95) == 48.0
    assert percentile(xs, 25) == 20.0


def test_percentile_sorts_input_nondestructively():
    """Input order doesn't matter; original list isn't mutated."""
    xs = [50.0, 10.0, 30.0, 40.0, 20.0]
    snap = list(xs)
    result = percentile(xs, 50)
    assert result == 30.0
    assert xs == snap  # not mutated


def test_percentile_handles_duplicates():
    """Duplicate values handled correctly — interpolation still works."""
    assert percentile([5.0, 5.0, 5.0], 50) == 5.0
    assert percentile([5.0, 5.0, 5.0], 95) == 5.0
