"""Panel assembly: a gapless hourly grid, honest NaNs, no lookahead."""

from __future__ import annotations

import pandas as pd

from features import panel as panel_mod
from models import fixtures


def test_missing_hours_become_explicit_nans_not_a_shifted_index():
    idx = pd.date_range("2026-01-01", periods=48, freq="h", tz="UTC")
    series = pd.Series(range(48), index=idx, dtype="float64").drop(index=idx[10:13])

    grid = panel_mod.to_hourly_grid(series)

    assert len(grid) == 48, "the grid must span the full range"
    assert grid.isna().sum() == 3
    assert (grid.index == idx).all()


def test_temperature_joins_without_extending_the_demand_grid():
    demand = pd.Series(1.0, index=pd.date_range("2026-01-01", periods=24, freq="h", tz="UTC"))
    temperature = pd.Series(
        5.0, index=pd.date_range("2025-12-30", periods=24 * 5, freq="h", tz="UTC")
    )

    built = panel_mod.build_panel(demand, temperature)

    assert len(built) == 24
    assert built["temperature_c"].notna().all()


def test_calendar_columns_are_functions_of_the_timestamp_alone():
    demand = pd.Series(1.0, index=pd.date_range("2026-01-03", periods=48, freq="h", tz="UTC"))
    built = panel_mod.build_panel(demand)

    saturday = built.loc["2026-01-03 00:00+00:00"]
    assert saturday["hour"] == 0
    assert saturday["dayofweek"] == 5
    assert saturday["is_weekend"] == 1


def test_synthetic_fixture_is_deterministic_and_hourly():
    a = fixtures.synthetic_series(end=pd.Timestamp("2026-06-01", tz="UTC"), days=30)
    b = fixtures.synthetic_series(end=pd.Timestamp("2026-06-01", tz="UTC"), days=30)

    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 30 * 24 + 1
    assert a.index.freq is None or a.index.inferred_freq == "h"


def test_describe_panel_reports_gaps():
    idx = pd.date_range("2026-01-01", periods=48, freq="h", tz="UTC")
    series = pd.Series(range(48), index=idx, dtype="float64").drop(index=idx[5:9])

    summary = panel_mod.describe_panel(panel_mod.build_panel(series))

    assert summary["rows"] == 48
    assert summary["missing_demand_hours"] == 4
    assert summary["has_temperature"] is False
