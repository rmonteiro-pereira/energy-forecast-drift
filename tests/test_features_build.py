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


# --------------------------------------------------------------------------
# Forecast weather at the target hour
#
# These features are the one exception to "read nothing at or after the
# origin", and the exception is only sound because the value was *published*
# before the origin. Everything below exists to keep that true.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def forecast_panel() -> pd.DataFrame:
    frame = fixtures.synthetic_series(days=60)
    return panel_mod.build_panel(
        frame["demand_mwh"], frame["temperature_c"], fixtures.synthetic_forecast(frame)
    )


def _origin_at_hour(panel: pd.DataFrame, hour: int) -> pd.Timestamp:
    room = panel.index < panel.index.max() - pd.Timedelta(days=3)
    return panel.index[(panel.index.hour == hour) & room][-1]


def test_the_forecast_feature_reads_the_forecast_and_not_what_happened(forecast_panel):
    """The leak test the observed features pass, applied to the forecast ones.

    Poison every *observation* from the origin onwards. A feature that quietly
    used the actual temperature at the target hour — a perfect forecast — would
    have to move. None may. Then poison the forecast itself, which must move:
    a column wired to nothing would pass the first half trivially.
    """
    origin = _origin_at_hour(forecast_panel, 18)
    columns = list(build_mod.FEATURE_COLUMNS)
    clean = build_mod.build_design_matrix(forecast_panel, pd.DatetimeIndex([origin]), HORIZONS)

    observed = forecast_panel.copy()
    observed.loc[observed.index >= origin, ["demand_mwh", "temperature_c"]] = 1e9
    unmoved = build_mod.build_design_matrix(observed, pd.DatetimeIndex([origin]), HORIZONS)
    pd.testing.assert_frame_equal(clean[columns], unmoved[columns])

    predicted = forecast_panel.copy()
    predicted.loc[predicted.index >= origin, panel_mod.FORECAST_TEMPERATURE_COLUMN] = 1e9
    moved = build_mod.build_design_matrix(predicted, pd.DatetimeIndex([origin]), HORIZONS)
    assert (moved["temp_fcst_target"] == 1e9).any(), "the forecast column is not wired to anything"


def test_a_forecast_the_origin_could_not_have_seen_yet_is_blanked(forecast_panel):
    """At 06:00 the run covering tomorrow does not exist yet; at 18:00 it does.

    `FORECAST_PUBLISHED_HOUR_UTC` is midday, so an origin earlier than that
    cannot have the next day's forecast — and every horizon that crosses
    midnight has to come back empty.
    """
    early = _origin_at_hour(forecast_panel, 6)
    design = build_mod.build_design_matrix(forecast_panel, pd.DatetimeIndex([early]), HORIZONS)
    crosses_midnight = design["target_utc"].dt.date > early.date()

    assert crosses_midnight.any() and (~crosses_midnight).any(), (
        "the case under test is not covered"
    )
    assert design.loc[crosses_midnight, "temp_fcst_target"].isna().all()
    assert design.loc[~crosses_midnight, "temp_fcst_target"].notna().all()

    late = _origin_at_hour(forecast_panel, 18)
    after_publication = build_mod.build_design_matrix(
        forecast_panel, pd.DatetimeIndex([late]), HORIZONS
    )
    assert after_publication["temp_fcst_target"].notna().all()


def test_every_forecast_feature_obeys_the_same_mask(forecast_panel):
    """One mask, applied once — not six chances to get it individually wrong."""
    early = _origin_at_hour(forecast_panel, 6)
    design = build_mod.build_design_matrix(forecast_panel, pd.DatetimeIndex([early]), HORIZONS)

    reference = design["temp_fcst_target"].isna()
    for feature in build_mod.FORECAST_FEATURES:
        assert design[feature].isna().equals(reference), f"{feature} is masked differently"


def test_the_publication_instant_is_the_day_before_not_the_hour_before(forecast_panel):
    """A run covers a whole day, so the gate is per target *day*, not per hour."""
    targets = pd.DatetimeIndex(
        ["2026-06-10T00:00", "2026-06-10T13:00", "2026-06-10T23:00"], tz="UTC"
    )
    published = build_mod.forecast_published_at(targets)

    assert published.nunique() == 1
    assert published[0] == pd.Timestamp("2026-06-09T12:00", tz="UTC")


def test_the_schema_is_stable_when_the_forecast_leg_has_never_run(panel, origin):
    """An older lake has no forecast dataset; the design matrix must not shrink."""
    design = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)

    assert list(design.columns) == list(build_mod.DESIGN_COLUMNS)
    for feature in build_mod.FORECAST_FEATURES:
        assert design[feature].isna().all()


def test_the_design_matrix_has_no_duplicated_columns(panel, origin):
    """`horizon_h` is both a key and a feature — it must appear exactly once."""
    design = build_mod.build_design_matrix(panel, pd.DatetimeIndex([origin]), HORIZONS)

    assert list(design.columns) == list(dict.fromkeys(design.columns))
    assert list(build_mod.feature_frame(design).columns) == list(build_mod.FEATURE_COLUMNS)
