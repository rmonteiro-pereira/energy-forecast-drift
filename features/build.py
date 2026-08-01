"""Design matrix for the global model — every feature is stamped with an origin.

The contract
------------
A row of the design matrix is one *(origin, horizon)* pair:

    origin_utc = O   the instant the forecast is made
    horizon_h  = h   how far ahead we forecast
    target_utc = T   = O + h, the hour being forecast

and the rule that makes the whole thing honest is:

    **every feature on that row is a function of data strictly before O.**

Not before `T` — before `O`. That distinction is where time-series feature
engineering usually leaks: a lag of 24 h looks innocent, but for a 24 h-ahead
forecast `T - 24h` *is* the origin, an hour that has not finished yet. So lags
here are computed against the target and then **masked out when they would
reach the origin or beyond**; LightGBM consumes the resulting NaN natively, and
`horizon_h` is itself a feature, so the model learns that far horizons simply
have less to go on.

Feature groups
--------------
* **calendar** — hour, day of week, month, weekend, US federal holiday. Pure
  functions of `T`; no data is read at all, so they cannot leak.
* **target-anchored lags** — demand at `T-24h`, `T-48h`, `T-168h`, `T-336h`
  and the mean of the same hour-of-week over the last four weeks. Masked as
  described above.
* **origin-anchored rolling stats** — the last observed hour and the mean /
  std / min / max of demand over the 24 h and 168 h *ending at `O-1h`*.
* **temperature** — the same two shapes, from the Open-Meteo leg.
* **forecast weather at the target hour** — see below.

Weather at the target hour, without cheating
--------------------------------------------
Load is dominated by temperature, and for most of this project's life the model
could not see the target hour's weather at all: every weather feature looked
backwards, so a 24 h-ahead forecast knew yesterday was warm and had no idea a
heat wave was arriving. That was a deliberate placeholder, not an oversight —
using the *observed* temperature at `T` would have been a perfect forecast, and
a backtest built on one is a lie.

The way out is not to use the weather at `T`, but the **forecast** of the
weather at `T`, as it was published before `O`. Open-Meteo archives exactly
that: `ingest.openmeteo.fetch_weather_forecast` stores what the day-before model
run predicted, in a dataset the reanalysis can never overwrite. Those values
carry genuine forecast error — around 1.5 °C against what actually happened —
which is precisely the uncertainty a real day-ahead forecaster carries.

So the rule at the top of this module is unchanged and still exact. A `fcst_`
column is *indexed* at `T` but was *published* before `O`, and it is masked out
on any row where that is not true — see `FORECAST_PUBLISHED_HOUR_UTC`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.typing import Rolling
from pandas.tseries.holiday import USFederalHolidayCalendar

from features.panel import (
    DEMAND_COLUMN,
    FORECAST_SPREAD_COLUMN,
    FORECAST_TEMPERATURE_COLUMN,
    TEMPERATURE_COLUMN,
)

# PJM's footprint is Eastern time; a holiday is a *local* calendar day, so the
# UTC timestamp is converted before the flag is looked up.
LOCAL_TZ = "America/New_York"

KEY_COLUMNS = ("origin_utc", "horizon_h", "target_utc")
TARGET_COLUMN = "y"

# Lags read at the *target* time, masked when they would touch the origin.
DEMAND_TARGET_LAGS = (24, 48, 168, 336)
TEMPERATURE_TARGET_LAGS = (168,)
# Same hour of the week, averaged over the last four weeks.
SEASON_OF_WEEK_LAGS = (168, 336, 504, 672)

CALENDAR_FEATURES = ("hour", "dayofweek", "month", "is_weekend", "is_holiday")
CATEGORICAL_FEATURES = ("hour", "dayofweek", "month")

# When the day-before model run is treated as published.
#
# Global NWP 00Z runs are on the wire by roughly 04:00-06:00 UTC. We hold the
# value back until 12:00 UTC — about twice the real delay. The conservatism is
# deliberate and one-directional: being late can only withhold information the
# model would legitimately have had, never grant information it would not. A
# leak here would be invisible in every metric and would inflate the headline
# number, so the error budget is spent entirely on the safe side.
FORECAST_PUBLISHED_HOUR_UTC = 12

# panel column -> feature name. Read at the target hour, masked by publication.
FORECAST_FEATURE_SOURCES: dict[str, str] = {
    FORECAST_TEMPERATURE_COLUMN: "temp_fcst_target",
    FORECAST_SPREAD_COLUMN: "temp_fcst_spread_target",
    "fcst_humidity_pct": "humidity_fcst_target",
    "fcst_dewpoint_c": "dewpoint_fcst_target",
    "fcst_wind_kmh": "wind_fcst_target",
    "fcst_cloud_pct": "cloud_fcst_target",
}

# Forecast temperature minus what it actually was at the same hour last week.
# Trees split on levels; this hands them the *change* directly, which is what
# separates "hot, as usual for August" from "a heat wave is arriving".
FORECAST_ANOMALY_FEATURE = "temp_fcst_target_minus_lag_168h"

FORECAST_FEATURES = (*FORECAST_FEATURE_SOURCES.values(), FORECAST_ANOMALY_FEATURE)

FEATURE_COLUMNS = (
    "horizon_h",
    *CALENDAR_FEATURES,
    *(f"demand_lag_{k}h" for k in DEMAND_TARGET_LAGS),
    "demand_same_hour_of_week_mean_4w",
    "demand_last_1h",
    "demand_roll_mean_24h",
    "demand_roll_std_24h",
    "demand_roll_min_24h",
    "demand_roll_max_24h",
    "demand_roll_mean_168h",
    *(f"temp_lag_{k}h" for k in TEMPERATURE_TARGET_LAGS),
    "temp_last_1h",
    "temp_roll_mean_24h",
    *FORECAST_FEATURES,
)

# Longest reach into the past any feature needs; origins younger than this
# would produce a mostly-NaN row.
MIN_HISTORY_HOURS = max(SEASON_OF_WEEK_LAGS)

# `horizon_h` is both a key and a feature, so the layout is de-duplicated once
# here rather than in every consumer.
DESIGN_COLUMNS = tuple(dict.fromkeys([*KEY_COLUMNS, *FEATURE_COLUMNS, TARGET_COLUMN]))


def _holiday_flag(targets: pd.DatetimeIndex) -> np.ndarray:
    """1 when `target` falls on a US federal holiday in local (Eastern) time."""
    if len(targets) == 0:
        return np.zeros(0, dtype="int8")

    local_days = targets.tz_convert(LOCAL_TZ).tz_localize(None).normalize()
    holidays = USFederalHolidayCalendar().holidays(
        start=local_days.min() - pd.Timedelta(days=1),
        end=local_days.max() + pd.Timedelta(days=1),
    )
    return local_days.isin(holidays).astype("int8")


def forecast_published_at(targets: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """When the day-before run covering each `target` is treated as available.

    A single instant per target day, not per hour: the run is one object and it
    covers the whole day at once.
    """
    return (
        targets.floor("D") - pd.Timedelta(days=1) + pd.Timedelta(hours=FORECAST_PUBLISHED_HOUR_UTC)
    )


def _rolling_before(series: pd.Series, window: int) -> Rolling:
    """Rolling window over the `window` hours **ending at the previous hour**.

    Evaluated at `O`, it covers `[O-window, O-1]` — strictly before the origin.
    """
    return series.shift(1).rolling(window, min_periods=max(2, window // 2))


def _lag_at_target(
    series: pd.Series,
    targets: pd.DatetimeIndex,
    origins: pd.DatetimeIndex,
    lag_hours: int,
) -> np.ndarray:
    """`series[target - lag]`, blanked out when that instant is not < origin."""
    source = targets - pd.Timedelta(hours=lag_hours)
    values = series.reindex(source).to_numpy(dtype="float64")
    return np.where(source < origins, values, np.nan)


def training_origins(
    index: pd.DatetimeIndex,
    *,
    stride_hours: int = 6,
    min_history_hours: int = MIN_HISTORY_HOURS,
    max_horizon: int = 24,
) -> pd.DatetimeIndex:
    """Forecast origins used to *train* — every `stride_hours` over the history.

    The evaluation origins are the backtest's own daily cutoffs; these extra,
    denser origins only ever supply training rows, and a row is only ever
    trained on once its target is in the past relative to the fold cutoff.
    """
    if len(index) == 0:
        return pd.DatetimeIndex([], tz="UTC")

    first = index.min() + pd.Timedelta(hours=min_history_hours)
    last = index.max() - pd.Timedelta(hours=max_horizon)
    if first > last:
        return pd.DatetimeIndex([], tz="UTC")
    return pd.date_range(first.ceil("h"), last, freq=f"{stride_hours}h")


def build_design_matrix(
    panel: pd.DataFrame,
    origins: pd.DatetimeIndex,
    horizons: tuple[int, ...] = tuple(range(1, 25)),
) -> pd.DataFrame:
    """One row per (origin, horizon): features known at `origin`, label at `target`.

    `panel` must be the gapless hourly panel from `features.panel.build_panel`.
    The label column `y` is the actual demand at `target_utc`, left NaN when the
    hour has not happened yet — callers drop those rows before fitting.
    """
    origins = pd.DatetimeIndex(origins)
    horizons = tuple(sorted(horizons))
    if len(origins) == 0 or not horizons:
        return pd.DataFrame(columns=list(DESIGN_COLUMNS))

    demand = panel[DEMAND_COLUMN].astype("float64")
    if TEMPERATURE_COLUMN in panel.columns:
        temperature = panel[TEMPERATURE_COLUMN].astype("float64")
    else:  # no weather leg yet — keep the schema stable, all-NaN
        temperature = pd.Series(np.nan, index=panel.index, dtype="float64")

    origin_col = pd.DatetimeIndex(np.repeat(origins.to_numpy(), len(horizons)), tz="UTC")
    horizon_col = np.tile(np.asarray(horizons, dtype="int16"), len(origins))
    target_col = origin_col + pd.to_timedelta(horizon_col, unit="h")

    out = pd.DataFrame(
        {
            "origin_utc": origin_col,
            "horizon_h": horizon_col,
            "target_utc": target_col,
        }
    )

    # --- calendar: functions of the target timestamp alone -------------------
    out["hour"] = target_col.hour.astype("int16")
    out["dayofweek"] = target_col.dayofweek.astype("int16")
    out["month"] = target_col.month.astype("int16")
    out["is_weekend"] = (target_col.dayofweek >= 5).astype("int8")
    out["is_holiday"] = _holiday_flag(target_col)

    # --- lags read at the target, masked back to the origin ------------------
    for lag in DEMAND_TARGET_LAGS:
        out[f"demand_lag_{lag}h"] = _lag_at_target(demand, target_col, origin_col, lag)
    for lag in TEMPERATURE_TARGET_LAGS:
        out[f"temp_lag_{lag}h"] = _lag_at_target(temperature, target_col, origin_col, lag)

    # Mean of the available weekly lags, NaN when none of them are — spelled out
    # rather than via nanmean so an all-missing row is a value, not a warning.
    season = np.vstack(
        [_lag_at_target(demand, target_col, origin_col, lag) for lag in SEASON_OF_WEEK_LAGS]
    )
    present = np.isfinite(season)
    counts = present.sum(axis=0)
    totals = np.where(present, season, 0.0).sum(axis=0)
    out["demand_same_hour_of_week_mean_4w"] = np.where(
        counts > 0, totals / np.maximum(counts, 1), np.nan
    )

    # --- rolling statistics of the history available at the origin -----------
    at_origin = {
        "demand_last_1h": demand.shift(1),
        "demand_roll_mean_24h": _rolling_before(demand, 24).mean(),
        "demand_roll_std_24h": _rolling_before(demand, 24).std(),
        "demand_roll_min_24h": _rolling_before(demand, 24).min(),
        "demand_roll_max_24h": _rolling_before(demand, 24).max(),
        "demand_roll_mean_168h": _rolling_before(demand, 168).mean(),
        "temp_last_1h": temperature.shift(1),
        "temp_roll_mean_24h": _rolling_before(temperature, 24).mean(),
    }
    for name, series in at_origin.items():
        out[name] = series.reindex(origin_col).to_numpy(dtype="float64")

    # --- forecast weather at the target, gated on publication ----------------
    # These are the only features read at `T` rather than before `O`, and they
    # are legitimate for one reason only: the value was published before `O`.
    # Where that is not true the row is blanked, exactly like a lag that would
    # reach into the origin.
    available = np.asarray(forecast_published_at(target_col) <= origin_col)
    for panel_column, feature in FORECAST_FEATURE_SOURCES.items():
        if panel_column in panel.columns:
            values = (
                panel[panel_column].astype("float64").reindex(target_col).to_numpy(dtype="float64")
            )
        else:  # the forecast leg has not run — keep the schema stable, all-NaN
            values = np.full(len(out), np.nan)
        out[feature] = np.where(available, values, np.nan)

    # Derived from two already-masked columns, so it inherits both masks.
    out[FORECAST_ANOMALY_FEATURE] = out["temp_fcst_target"] - out["temp_lag_168h"]

    out[TARGET_COLUMN] = demand.reindex(target_col).to_numpy(dtype="float64")
    return out[list(DESIGN_COLUMNS)]


def feature_frame(design: pd.DataFrame) -> pd.DataFrame:
    """The model-facing view: features only, categoricals typed as such."""
    features = design[list(FEATURE_COLUMNS)].copy()
    for column in CATEGORICAL_FEATURES:
        features[column] = features[column].astype("int16")
    return features
