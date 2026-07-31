"""`drift_timeline` asserted for content, not shape.

Written to kill a named mutation gap. The existing tests checked that the
timeline had points and that the points had keys; every mutation to the trailing
window bounds, the feature-eligibility filter and the `min_samples` skip survived,
because nothing asserted *which rows land in which window*.

That matters more than it sounds. The timeline is the series the dashboard plots
to answer "since when" — the question anyone actually asks when an alarm fires.
A window that silently includes a day too many, or excludes the boundary day,
shifts the whole story of when drift started.

The fixture is constructed rather than fitted: `drift_timeline` is a pure
function of a scored frame, so building the frame directly makes the boundary
explicit in the test instead of hiding it inside a booster.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from drift import detectors
from drift.config import DEFAULT_THRESHOLDS
from drift.windows import (
    ABS_ERROR_COLUMN,
    ABS_PCT_ERROR_COLUMN,
    ERROR_COLUMN,
    PREDICTION_COLUMN,
    ScoredWindows,
)
from features import build as build_mod

T = DEFAULT_THRESHOLDS

#: Rows per day in the fixture: one per hour.
PER_DAY = 24

#: The window-bound tests use a thresholds object with `min_samples` lowered to
#: 1, deliberately. The shipped 200 would skip every window in a fixture this
#: size, which is what made an earlier draft of these tests pass vacuously --
#: they asserted over an empty list. The `min_samples` filter is worth testing,
#: but it is a *different* property, and mixing the two hides both.
BOUNDS = dataclasses.replace(DEFAULT_THRESHOLDS, min_samples=1)


def _scored(start: str, days: int, *, demand: float = 100_000.0) -> pd.DataFrame:
    """A scored frame with `days` whole days of hourly rows, one per hour."""
    n = days * PER_DAY
    target = pd.date_range(start, periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(7)
    jitter = rng.normal(0.0, 500.0, n)

    frame = pd.DataFrame(
        {
            "target_utc": target,
            build_mod.TARGET_COLUMN: demand + jitter,
            PREDICTION_COLUMN: demand + jitter * 0.5,
            ERROR_COLUMN: jitter * -0.5,
            ABS_ERROR_COLUMN: np.abs(jitter * 0.5),
            ABS_PCT_ERROR_COLUMN: np.abs(jitter * 0.5) / demand * 100.0,
        }
    )
    # One real (non-deterministic) feature column, plus one deterministic one
    # that must be filtered out of the feature scan.
    frame[build_mod.FEATURE_COLUMNS[0]] = demand + jitter
    frame["hour"] = target.hour
    return frame


def _windows(reference: pd.DataFrame, current: pd.DataFrame) -> ScoredWindows:
    return ScoredWindows(reference=reference, current=current, booster=None, split={}, train_rows=0)


# ---------------------------------------------------------------------------
# the trailing window bounds
# ---------------------------------------------------------------------------
def test_a_point_counts_exactly_the_trailing_window_and_not_a_day_more():
    """`(day - span, day]` — half-open below, inclusive at `day`.

    With `window_days=3` and whole hourly days, the point for day *d* must cover
    days d-2, d-1 and d: exactly 3 x 24 rows. Off-by-one in either bound changes
    this count, which is what the mutants did undetected.
    """
    windows = _windows(_scored("2026-01-01", 6), _scored("2026-01-07", 4))
    points = detectors.drift_timeline(windows, BOUNDS, window_days=3)

    assert points, "no timeline points were produced"
    full = [p for p in points if p["n"] != 3 * PER_DAY]
    # The first two days cannot have a full trailing window behind them.
    assert all(p["n"] < 3 * PER_DAY for p in points[:2]), (
        f"early points should have partial windows, got {[p['n'] for p in points[:2]]}"
    )
    assert all(p["n"] == 3 * PER_DAY for p in points[2:]), (
        f"every later point must cover exactly {3 * PER_DAY} rows, got "
        f"{[p['n'] for p in points[2:]]}"
    )
    assert len(full) == 2, "exactly the first two points should be partial"


def test_the_window_grows_by_one_day_per_day_until_it_saturates():
    """A direct check on the lower bound: `> day - span`, not `>=`."""
    windows = _windows(_scored("2026-01-01", 5), _scored("2026-01-06", 2))
    points = detectors.drift_timeline(windows, BOUNDS, window_days=4)

    counts = [p["n"] for p in points]
    expected_prefix = [1 * PER_DAY, 2 * PER_DAY, 3 * PER_DAY]
    assert counts[:3] == expected_prefix, (
        f"the window should grow one day at a time: expected {expected_prefix}, got {counts[:3]}"
    )
    assert all(c == 4 * PER_DAY for c in counts[3:]), (
        f"once saturated every window holds {4 * PER_DAY} rows, got {counts[3:]}"
    )


def test_one_point_per_day_in_order():
    windows = _windows(_scored("2026-01-01", 4), _scored("2026-01-05", 3))
    points = detectors.drift_timeline(windows, BOUNDS, window_days=2)

    days = [p["day_utc"] for p in points]
    assert days == sorted(days), "points must be ordered by day"
    assert len(days) == len(set(days)), "each day appears exactly once"


def test_the_window_label_marks_where_the_day_came_from():
    windows = _windows(_scored("2026-01-01", 4), _scored("2026-01-05", 3))
    points = detectors.drift_timeline(windows, BOUNDS, window_days=2)

    labels = [p["window"] for p in points]
    assert set(labels) <= {"reference", "current"}
    assert labels[0] == "reference", "the series must start in the reference window"
    assert labels[-1] == "current", "the series must end in the current window"


# ---------------------------------------------------------------------------
# the min_samples skip
# ---------------------------------------------------------------------------
def test_days_below_min_samples_are_skipped_entirely():
    """A trailing window under `min_samples` produces no point at all.

    Straddled deliberately: at 48 the first day (24 trailing rows) is below and
    every later day is at or above, so the filter has something to do. Asserting
    against the shipped 200 here would produce an empty list and a test that
    passes because nothing happened.
    """
    windows = _windows(_scored("2026-01-01", 6), _scored("2026-01-07", 4))
    straddle = dataclasses.replace(T, min_samples=2 * PER_DAY)
    points = detectors.drift_timeline(windows, straddle, window_days=3)

    assert points, "the threshold was set too high for the fixture to say anything"
    assert all(p["n"] >= straddle.min_samples for p in points), (
        f"a point was emitted below min_samples={straddle.min_samples}: "
        f"{[p['n'] for p in points if p['n'] < straddle.min_samples]}"
    )

    first_day = pd.Timestamp("2026-01-01", tz="UTC").isoformat()
    assert all(p["day_utc"] != first_day for p in points), (
        "the first day has only 24 trailing rows and must be skipped"
    )


def test_the_shipped_min_samples_would_reject_this_whole_fixture():
    """Proves the filter is live rather than incidentally satisfied.

    Ten days of hourly rows never reach 200 in a 3-day trailing window, so the
    production threshold empties the series. If this ever returns points, either
    `min_samples` moved or the filter stopped being applied.
    """
    windows = _windows(_scored("2026-01-01", 6), _scored("2026-01-07", 4))
    assert T.min_samples > 3 * PER_DAY
    assert detectors.drift_timeline(windows, T, window_days=3) == []


def test_raising_min_samples_removes_points_from_the_front():
    reference, current = _scored("2026-01-01", 6), _scored("2026-01-07", 4)

    lenient = detectors.drift_timeline(
        _windows(reference, current), dataclasses.replace(T, min_samples=1), window_days=3
    )
    strict = detectors.drift_timeline(
        _windows(reference, current),
        dataclasses.replace(T, min_samples=3 * PER_DAY),
        window_days=3,
    )
    assert len(strict) < len(lenient), (
        "a higher min_samples must drop the partial windows at the start"
    )
    assert all(p["n"] >= 3 * PER_DAY for p in strict)


# ---------------------------------------------------------------------------
# feature eligibility
# ---------------------------------------------------------------------------
def test_deterministic_columns_are_excluded_from_the_feature_scan():
    """`hour` is a function of the timestamp; it must never be the worst feature."""
    windows = _windows(_scored("2026-01-01", 6), _scored("2026-01-07", 4))
    points = detectors.drift_timeline(windows, BOUNDS, window_days=3)

    assert points
    chosen = {p["feature_max_column"] for p in points}
    assert "hour" not in chosen, (
        "a deterministic calendar column was scanned as a feature — its PSI "
        "measures which dates the window covers, not the data"
    )
    assert chosen <= set(build_mod.FEATURE_COLUMNS) | {None}


def test_a_frame_with_no_eligible_features_still_produces_points():
    """Feature PSI goes None; the target and prediction series must survive."""
    windows = _windows(_scored("2026-01-01", 6), _scored("2026-01-07", 4))
    stripped = _windows(
        windows.reference.drop(columns=[build_mod.FEATURE_COLUMNS[0]]),
        windows.current.drop(columns=[build_mod.FEATURE_COLUMNS[0]]),
    )
    points = detectors.drift_timeline(stripped, BOUNDS, window_days=3)

    assert points, "dropping the only feature must not empty the timeline"
    assert all(p["feature_max_psi"] is None for p in points)
    assert all(p["feature_max_column"] is None for p in points)
    assert all(isinstance(p["target_psi"], float) for p in points)


def test_an_empty_frame_yields_no_points_rather_than_raising():
    empty = _scored("2026-01-01", 0)
    assert detectors.drift_timeline(_windows(empty, empty), BOUNDS) == []


def test_the_reported_mae_is_that_day_and_not_the_whole_window():
    """`mae` comes from `rows` (the day), while `n` comes from `trailing`."""
    reference = _scored("2026-01-01", 6)
    current = _scored("2026-01-07", 4)
    # Make one day's error unmistakable.
    spike_day = pd.Timestamp("2026-01-08", tz="UTC")
    mask = pd.DatetimeIndex(current["target_utc"]).floor("D") == spike_day
    current.loc[mask, ABS_ERROR_COLUMN] = 9_999.0

    points = detectors.drift_timeline(_windows(reference, current), BOUNDS, window_days=3)
    spike = [p for p in points if p["day_utc"] == spike_day.isoformat()]
    assert spike, "the spiked day produced no point"
    assert spike[0]["mae"] == pytest.approx(9_999.0), (
        "the reported MAE must describe the day, not the whole trailing window"
    )
