"""The backtest's arithmetic and fold accounting, pinned against real values.

Two named mutation gaps, both cases where a test existed and was too weak to
earn its green tick:

* **The MAPE formula.** The only assertion on it was
  `result.overall["mape_pct"] == approx(0.0)` — from a *perfect* forecast. Zero
  divided by anything is zero, so that assertion holds for any scaling, any
  denominator, and several outright wrong formulas. Every mutation to
  `(abs_error / |actual|) * 100` survived.

* **Skipped-fold accounting.** The only assertion was `skipped_folds >= 1`,
  which passes if the counter increments by two, or if a different fold is
  skipped, or if several are. Existence was checked; correctness was not.

Both are now pinned to arithmetic worked out by hand, so the assertion fails if
the number is wrong rather than merely absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models import backtest


def _series(hours: int, value: float = 100.0, start: str = "2026-01-01") -> pd.Series:
    index = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    return pd.Series(np.full(hours, value, dtype="float64"), index=index)


def _biased(offset: float):
    """A predictor that is wrong by exactly `offset` at every horizon."""

    def predict(history: pd.Series, targets: pd.DatetimeIndex, cutoff: pd.Timestamp) -> pd.Series:
        return pd.Series(np.full(len(targets), history.iloc[-1] + offset), index=targets)

    return predict


# ---------------------------------------------------------------------------
# the MAPE formula
# ---------------------------------------------------------------------------
def test_mape_is_the_absolute_percentage_of_the_actual():
    """A flat 100 MWh series mispredicted by exactly 10 gives MAPE of exactly 10%.

    Worked out by hand: |110 - 100| / |100| * 100 = 10.0. This is the assertion
    the previous perfect-forecast test could not make — it pins the numerator,
    the denominator, the absolute value and the *100 all at once.
    """
    series = _series(24 * 30)
    result = backtest.run(series, _biased(10.0), horizons=(1, 2, 3), weeks=1, min_history_hours=24)

    assert result.overall["mape_pct"] == pytest.approx(10.0), (
        "MAPE must be |error| / |actual| * 100 — a formula that drops the *100, "
        "divides by the prediction, or forgets the absolute value all give a "
        "different number here"
    )
    assert result.overall["mae"] == pytest.approx(10.0)


def test_mape_scales_with_the_error_not_with_the_level():
    """Doubling the error doubles MAPE; doubling the level halves it."""
    base = backtest.run(
        _series(24 * 30, 100.0), _biased(10.0), horizons=(1,), weeks=1, min_history_hours=24
    )
    twice_the_error = backtest.run(
        _series(24 * 30, 100.0), _biased(20.0), horizons=(1,), weeks=1, min_history_hours=24
    )
    twice_the_level = backtest.run(
        _series(24 * 30, 200.0), _biased(10.0), horizons=(1,), weeks=1, min_history_hours=24
    )

    assert base.overall["mape_pct"] == pytest.approx(10.0)
    assert twice_the_error.overall["mape_pct"] == pytest.approx(20.0)
    assert twice_the_level.overall["mape_pct"] == pytest.approx(5.0)


def test_a_negative_error_gives_the_same_mape_as_a_positive_one():
    """The absolute value, pinned. Bias keeps the sign; MAPE must not."""
    over = backtest.run(
        _series(24 * 30), _biased(10.0), horizons=(1,), weeks=1, min_history_hours=24
    )
    under = backtest.run(
        _series(24 * 30), _biased(-10.0), horizons=(1,), weeks=1, min_history_hours=24
    )

    assert over.overall["mape_pct"] == pytest.approx(under.overall["mape_pct"])
    assert over.overall["mae"] == pytest.approx(under.overall["mae"])
    assert over.overall["bias"] == pytest.approx(-under.overall["bias"])
    assert over.overall["bias"] != pytest.approx(0.0), "a biased predictor must show bias"


# ---------------------------------------------------------------------------
# fold accounting
# ---------------------------------------------------------------------------
def test_no_folds_are_skipped_when_the_series_is_complete():
    """The baseline the count is measured against."""
    result = backtest.run(
        _series(24 * 30), _biased(1.0), horizons=(1, 2), weeks=1, min_history_hours=24
    )
    assert result.skipped_folds == 0, f"a gapless series skipped {result.skipped_folds} fold(s)"
    assert result.warnings == []
    assert len(result.folds) == result.overall["n"] / 2


def test_exactly_one_skipped_fold_is_counted_once():
    """One hole, one skip -- not two, not zero.

    `skipped_folds >= 1` passed on a counter incrementing by two. An equality
    assertion does not.
    """
    series = _series(24 * 30)
    complete = backtest.run(series, _biased(1.0), horizons=(1,), weeks=1, min_history_hours=24)
    assert complete.skipped_folds == 0

    # Punch a single hole at one fold's only target hour.
    holed = series.copy()
    target = complete.folds[3] + pd.Timedelta(hours=1)
    holed.loc[target] = np.nan

    result = backtest.run(holed, _biased(1.0), horizons=(1,), weeks=1, min_history_hours=24)
    assert result.skipped_folds == 1, (
        f"one unscorable target hour should skip exactly one fold, got {result.skipped_folds}"
    )
    assert len(result.folds) == len(complete.folds) - 1, (
        "the skipped fold must be dropped from `folds`, not merely counted"
    )
    assert len(result.warnings) == 1
    assert (
        target.floor("D").isoformat()[:10] in result.warnings[0]
        or "unscorable" in result.warnings[0]
    )


def test_two_holes_in_different_folds_are_counted_twice():
    series = _series(24 * 30)
    reference = backtest.run(series, _biased(1.0), horizons=(1,), weeks=1, min_history_hours=24)

    holed = series.copy()
    for fold in (reference.folds[2], reference.folds[5]):
        holed.loc[fold + pd.Timedelta(hours=1)] = np.nan

    result = backtest.run(holed, _biased(1.0), horizons=(1,), weeks=1, min_history_hours=24)
    assert result.skipped_folds == 2, (
        f"two unscorable folds should count 2, got {result.skipped_folds}"
    )
    assert len(result.folds) == len(reference.folds) - 2


def test_a_series_with_every_fold_unscorable_raises_rather_than_reporting_nothing():
    """The `raise ValueError` path — reporting metrics over zero folds would be worse."""
    series = _series(24 * 30)
    reference = backtest.run(series, _biased(1.0), horizons=(1,), weeks=1, min_history_hours=24)

    holed = series.copy()
    for fold in reference.folds:
        holed.loc[fold + pd.Timedelta(hours=1)] = np.nan

    with pytest.raises(ValueError, match="unscorable"):
        backtest.run(holed, _biased(1.0), horizons=(1,), weeks=1, min_history_hours=24)
