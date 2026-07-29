"""The design matrix: a feature for target T may only use data before the origin.

This is the M2 version of the leakage guarantee. The M1 tests proved the
*backtest* never hands a model post-cutoff data; these prove the *feature
builder* cannot smuggle it in through a lag or a rolling window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import build as build_mod
from features import panel as panel_mod
from models import fixtures


def make_panel(days: int = 60) -> pd.DataFrame:
    frame = fixtures.synthetic_series(days=days)
    return panel_mod.build_panel(frame["demand_mwh"], frame["temperature_c"])


HORIZONS = tuple(range(1, 25))


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return make_panel()


@pytest.fixture(scope="module")
def origin(panel: pd.DataFrame) -> pd.Timestamp:
    return panel.index[-48]


def test_no_feature_moves_when_the_future_is_poisoned(panel, origin):
    """The central M2 rigour claim, tested the same way M1 tested the backtest.

    Replace every value from the origin onwards with garbage. If any feature
    reads at or after the origin, some column has to move. None may.
    """
    clean = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)

    poisoned_panel = panel.copy()
    poisoned_panel.loc[poisoned_panel.index >= origin, ["demand_mwh", "temperature_c"]] = 1e9
    poisoned = build_mod.build_design_matrix(poisoned_panel, pd.DatetimeIndex([origin]), HORIZONS)

    columns = list(build_mod.FEATURE_COLUMNS)
    pd.testing.assert_frame_equal(clean[columns], poisoned[columns])
    # Sanity: the poison did land somewhere — the labels are in the future.
    assert (poisoned["y"] == 1e9).all()


def test_the_hour_stamped_at_the_origin_is_never_read(panel, origin):
    """`< origin`, not `<= origin`: the origin hour itself is not complete yet."""
    poisoned_panel = panel.copy()
    poisoned_panel.loc[origin, "demand_mwh"] = 1e9

    clean = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)
    poisoned = build_mod.build_design_matrix(poisoned_panel, pd.DatetimeIndex([origin]), HORIZONS)

    columns = list(build_mod.FEATURE_COLUMNS)
    pd.testing.assert_frame_equal(clean[columns], poisoned[columns])


def test_a_lag_is_masked_exactly_when_it_would_touch_the_origin(panel, origin):
    """`demand_lag_24h` is real at h=23 and must vanish at h=24 (T-24h == origin)."""
    design = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)
    by_horizon = design.set_index("horizon_h")

    assert pd.notna(by_horizon.loc[23, "demand_lag_24h"])
    assert by_horizon.loc[23, "demand_lag_24h"] == pytest.approx(
        panel["demand_mwh"].loc[origin - pd.Timedelta(hours=1)]
    )
    assert pd.isna(by_horizon.loc[24, "demand_lag_24h"])


def test_the_weekly_lag_survives_every_horizon_in_the_protocol(panel, origin):
    """168h back from a 1-24h-ahead target is always at least 144h pre-origin."""
    design = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)

    assert design["demand_lag_168h"].notna().all()
    assert design["demand_same_hour_of_week_mean_4w"].notna().all()


def test_rolling_windows_end_one_hour_before_the_origin(panel, origin):
    design = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), (1,))
    window = panel["demand_mwh"].loc[
        origin - pd.Timedelta(hours=24) : origin - pd.Timedelta(hours=1)
    ]

    assert len(window) == 24
    assert design["demand_roll_mean_24h"].iloc[0] == pytest.approx(window.mean())
    assert design["demand_last_1h"].iloc[0] == pytest.approx(window.iloc[-1])
    assert design["demand_roll_max_24h"].iloc[0] == pytest.approx(window.max())


def test_calendar_columns_are_functions_of_the_target_timestamp_alone(panel, origin):
    """Wipe the data entirely; the calendar must be untouched."""
    blank = panel.copy()
    blank[["demand_mwh", "temperature_c"]] = np.nan

    clean = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)
    wiped = build_mod.build_design_matrix(blank, pd.DatetimeIndex([origin]), HORIZONS)

    calendar = list(build_mod.CALENDAR_FEATURES)
    pd.testing.assert_frame_equal(clean[calendar], wiped[calendar])
    assert (clean["hour"] == clean["target_utc"].dt.hour).all()
    assert (clean["is_weekend"] == (clean["target_utc"].dt.dayofweek >= 5).astype(int)).all()


def test_us_federal_holidays_are_flagged_in_local_time():
    idx = pd.date_range("2026-07-03", "2026-07-06", freq="h", tz="UTC")
    demand = pd.Series(1.0, index=idx)
    frame = panel_mod.build_panel(demand)
    design = build_mod.build_design_matrix(frame, pd.DatetimeIndex([idx[30]]), (1, 2, 3))

    local_days = design["target_utc"].dt.tz_convert(build_mod.LOCAL_TZ).dt.date
    for is_holiday, day in zip(design["is_holiday"], local_days, strict=True):
        assert bool(is_holiday) == (day == pd.Timestamp("2026-07-03").date())


def test_the_label_is_the_demand_at_the_target_hour(panel, origin):
    design = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)
    expected = panel["demand_mwh"].reindex(pd.DatetimeIndex(design["target_utc"])).to_numpy()

    np.testing.assert_allclose(design["y"].to_numpy(), expected)


def test_every_target_is_strictly_after_its_own_origin(panel):
    origins = build_mod.training_origins(panel.index, stride_hours=12)
    design = build_mod.build_design_matrix(panel, origins, HORIZONS)

    assert len(design) == len(origins) * len(HORIZONS)
    assert (design["target_utc"] > design["origin_utc"]).all()
    assert (
        design["target_utc"] - design["origin_utc"] == pd.to_timedelta(design["horizon_h"], "h")
    ).all()


def test_training_origins_leave_room_for_history_and_for_the_horizon(panel):
    origins = build_mod.training_origins(panel.index, stride_hours=6, max_horizon=24)

    assert origins.min() >= panel.index.min() + pd.Timedelta(hours=build_mod.MIN_HISTORY_HOURS)
    assert origins.max() <= panel.index.max() - pd.Timedelta(hours=24)
    assert set(np.diff(origins.to_numpy()).astype("timedelta64[h]").astype(int)) == {6}


def test_a_history_shorter_than_the_longest_lag_yields_no_origins():
    idx = pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC")
    frame = panel_mod.build_panel(pd.Series(1.0, index=idx))

    assert len(build_mod.training_origins(frame.index)) == 0
    assert build_mod.build_design_matrix(frame, pd.DatetimeIndex([]), HORIZONS).empty


def test_the_schema_is_stable_when_the_weather_leg_is_missing(panel, origin):
    demand_only = panel_mod.build_panel(panel["demand_mwh"])
    design = build_mod.build_design_matrix(demand_only, pd.DatetimeIndex([origin]), (1, 12, 24))

    assert list(design.columns) == list(build_mod.DESIGN_COLUMNS)
    assert design["temp_lag_168h"].isna().all()
    assert design["demand_lag_168h"].notna().all()


def test_the_design_matrix_has_no_duplicated_columns(panel, origin):
    """`horizon_h` is both a key and a feature — it must appear exactly once."""
    design = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)

    assert list(design.columns) == list(dict.fromkeys(design.columns))
    assert list(build_mod.feature_frame(design).columns) == list(build_mod.FEATURE_COLUMNS)
