"""Walk-forward mechanics, with the no-leakage property tested directly."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models import backtest, baseline


def series(days: int = 120) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=days * 24, freq="h", tz="UTC")
    hours = np.arange(len(idx))
    values = 100.0 + 10 * np.sin(2 * np.pi * hours / 24) + 3 * np.sin(2 * np.pi * hours / 168)
    return pd.Series(values, index=idx, name="demand_mwh")


def naive(history, targets, cutoff):
    return baseline.predict(history, targets, cutoff)


def test_folds_slide_daily_over_the_requested_window():
    result = backtest.run(series(), naive, weeks=8)

    assert len(result.folds) >= 8 * 7 - 1
    gaps = {(b - a) for a, b in zip(result.folds, result.folds[1:], strict=False)}
    assert gaps == {pd.Timedelta(days=1)}


def test_every_horizon_is_scored_on_the_same_folds():
    result = backtest.run(series(), naive, weeks=8)

    counts = set(result.by_horizon["n"])
    assert len(counts) == 1
    assert counts.pop() == len(result.folds)
    assert list(result.by_horizon["horizon_h"]) == list(range(1, 25))


def test_the_model_never_sees_data_at_or_after_the_cutoff():
    """The central rigour claim: information only flows forward."""
    seen: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def spy(history, targets, cutoff):
        seen.append((history.index.max(), cutoff))
        return baseline.predict(history, targets, cutoff)

    backtest.run(series(), spy, weeks=4)

    assert seen, "the spy model was never called"
    assert all(last < cutoff for last, cutoff in seen)


def test_future_values_cannot_change_the_result():
    """Corrupting everything after the last fold must not move the metrics."""
    clean = series()
    result_a = backtest.run(clean, naive, weeks=4)

    poisoned = clean.copy()
    last_target = result_a.predictions["target_utc"].max()
    poisoned[poisoned.index > last_target] = 1e9

    result_b = backtest.run(poisoned, naive, weeks=4)
    assert result_a.overall["mae"] == pytest.approx(result_b.overall["mae"])


def test_metrics_are_correct_on_a_hand_checkable_case():
    idx = pd.date_range("2026-01-01", periods=24 * 40, freq="h", tz="UTC")
    flat = pd.Series(np.full(len(idx), 200.0), index=idx)
    # Seasonal naive is exact on a constant series.
    result = backtest.run(flat, naive, weeks=2, horizons=(1, 2, 3))

    assert result.overall["mae"] == pytest.approx(0.0)
    assert result.overall["mape_pct"] == pytest.approx(0.0)


def test_short_history_fails_loudly_instead_of_scoring_nothing():
    with pytest.raises(ValueError, match="Not enough history"):
        backtest.run(series(days=5), naive, weeks=8)


def test_folds_with_gaps_are_skipped_not_silently_scored():
    data = series()
    # Punch a hole in the actuals of one fold's horizon window.
    hole = data.index[-24 * 10]
    data.loc[hole : hole + pd.Timedelta(hours=2)] = np.nan

    result = backtest.run(data, naive, weeks=8)

    assert result.skipped_folds >= 1
    assert result.warnings
    assert set(result.by_horizon["n"]) == {len(result.folds)}


def test_markdown_table_renders_every_horizon():
    result = backtest.run(series(), naive, weeks=4)
    table = backtest.markdown_table(result.by_horizon)

    assert table.count("\n") == 2 + 24 - 1
    assert "| Horizon (h) |" in table
