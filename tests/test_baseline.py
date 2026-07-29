"""The baseline itself, and the leakage guard it refuses to run without."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models import baseline


def weekly_series(weeks: int = 6) -> pd.Series:
    """A perfectly week-periodic series: seasonal naive must be exact on it."""
    idx = pd.date_range("2026-01-01", periods=weeks * 168, freq="h", tz="UTC")
    shape = np.tile(np.arange(168, dtype=float) * 10.0, weeks)
    return pd.Series(shape, index=idx, name="demand_mwh")


def test_exact_on_a_perfectly_weekly_series():
    series = weekly_series()
    cutoff = series.index[-25]
    targets = pd.DatetimeIndex([cutoff + pd.Timedelta(hours=h) for h in range(1, 25)])

    preds = baseline.predict(series[series.index < cutoff], targets, cutoff)

    pd.testing.assert_series_equal(
        preds, series.reindex(targets).rename("prediction"), check_freq=False
    )


def test_reads_exactly_one_week_back():
    series = weekly_series()
    cutoff = series.index[-25]
    target = pd.DatetimeIndex([cutoff + pd.Timedelta(hours=3)])

    preds = baseline.predict(series[series.index < cutoff], target, cutoff)

    expected = series.loc[target[0] - pd.Timedelta(hours=168)]
    assert preds.iloc[0] == expected


def test_rejects_history_that_reaches_the_cutoff():
    series = weekly_series()
    cutoff = series.index[-25]
    leaky = series[series.index <= cutoff]  # one hour too many

    with pytest.raises(baseline.TemporalLeakageError):
        baseline.predict(leaky, pd.DatetimeIndex([cutoff + pd.Timedelta(hours=1)]), cutoff)


def test_rejects_a_horizon_whose_seasonal_lag_lands_after_the_cutoff():
    series = weekly_series()
    cutoff = series.index[-200]
    # h = 169 would read the hour *after* the cutoff — the classic leak.
    far_target = pd.DatetimeIndex([cutoff + pd.Timedelta(hours=169)])

    with pytest.raises(baseline.TemporalLeakageError):
        baseline.predict(series[series.index < cutoff], far_target, cutoff)


def test_missing_lag_yields_nan_rather_than_a_wrong_number():
    series = weekly_series()
    cutoff = series.index[-25]
    history = series[series.index < cutoff].copy()
    hole = cutoff + pd.Timedelta(hours=1) - pd.Timedelta(hours=168)
    history = history.drop(index=hole)

    preds = baseline.predict(history, pd.DatetimeIndex([cutoff + pd.Timedelta(hours=1)]), cutoff)
    assert pd.isna(preds.iloc[0])
