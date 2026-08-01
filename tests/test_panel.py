"""Panel assembly: a gapless hourly grid, honest NaNs, no lookahead."""

from __future__ import annotations

import pandas as pd
import pytest

from features import panel as panel_mod
from ingest import config, openmeteo
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


# --------------------------------------------------------------------------
# Blending nine cities into one number
# --------------------------------------------------------------------------


def _weather_rows(values: dict[str, float], when: str = "2026-01-01T00:00") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site": list(values),
            "timestamp_utc": pd.Timestamp(when, tz="UTC"),
            "temperature_c": list(values.values()),
        }
    )


def test_the_blend_is_weighted_by_population_not_by_headcount():
    """Chicago outweighs Richmond by ~7x; a plain mean would treat them alike."""
    df = _weather_rows({"chicago_il": 0.0, "richmond_va": 10.0})

    blended = panel_mod.blend_by_site(df, ("temperature_c",))["temperature_c"].iloc[0]

    assert blended == pytest.approx(10.0 * 1.3 / (9.4 + 1.3))
    assert blended < 5.0, "an unweighted mean would have landed at 5.0"


def test_a_missing_city_renormalises_instead_of_dragging_the_blend():
    """A data gap must not read as weather.

    With Chicago absent, the remaining sites have to be rescaled to sum to 1.
    Without that, two thirds of the weight would silently contribute 0 °C and a
    mild hour would look freezing.
    """
    everyone_warm = _weather_rows({"philadelphia_pa": 20.0, "richmond_va": 20.0})

    blended = panel_mod.blend_by_site(everyone_warm, ("temperature_c",))["temperature_c"].iloc[0]

    assert blended == pytest.approx(20.0)


def test_a_site_nobody_configured_contributes_nothing():
    """An unknown key must weigh 0, not 1 — a typo cannot outvote Chicago."""
    df = _weather_rows({"philadelphia_pa": 20.0, "atlantis": -50.0})

    blended = panel_mod.blend_by_site(df, ("temperature_c",))["temperature_c"].iloc[0]

    assert blended == pytest.approx(20.0)


def test_the_spread_is_what_the_blend_throws_away():
    df = _weather_rows({"chicago_il": 8.0, "richmond_va": 28.0, "philadelphia_pa": 18.0})

    assert panel_mod.site_spread(df, "temperature_c").iloc[0] == pytest.approx(20.0)


def test_observations_and_forecasts_live_in_datasets_that_cannot_collide():
    """The separation is the safety property, so it is asserted, not assumed.

    `write_incremental` keeps the newest row for a key, and both datasets are
    keyed `(site, timestamp_utc)`. Sharing one table would mean the ERA5
    reanalysis overwrites the forecast the moment it catches up, silently
    turning `temp_fcst_target` into a perfect forecast.
    """
    assert config.WEATHER_HOURLY.name != config.WEATHER_FORECAST_HOURLY.name
    assert config.WEATHER_HOURLY.path != config.WEATHER_FORECAST_HOURLY.path
    assert "is_observed" not in openmeteo.FORECAST_COLUMNS


def test_the_forecast_panel_never_carries_an_observed_column():
    """Nothing named like an observation may reach the forecast side of the panel."""
    for column in panel_mod.FORECAST_PANEL_COLUMNS:
        assert column.startswith("fcst_"), f"{column} is not marked as a forecast"
    assert panel_mod.TEMPERATURE_COLUMN not in panel_mod.FORECAST_PANEL_COLUMNS


def test_the_forecast_joins_onto_the_panel_without_extending_it():
    demand = pd.Series(1.0, index=pd.date_range("2026-01-01", periods=24, freq="h", tz="UTC"))
    forecast = pd.DataFrame(
        {column: 1.0 for column in panel_mod.FORECAST_PANEL_COLUMNS},
        index=pd.date_range("2025-12-30", periods=24 * 5, freq="h", tz="UTC"),
    )

    built = panel_mod.build_panel(demand, None, forecast)

    assert len(built) == 24
    assert built[panel_mod.FORECAST_TEMPERATURE_COLUMN].notna().all()
    assert panel_mod.describe_panel(built)["has_weather_forecast"] is True
