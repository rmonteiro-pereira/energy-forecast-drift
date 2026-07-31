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

Note on weather: only *past* temperature is used. Open-Meteo does publish a
forecast (the lake even tags it `is_observed=False`), and a production forecaster
would legitimately feed tomorrow's forecast temperature in. We deliberately do
not, because it would make the "features at T use only data ≤ O" claim depend on
a second, unmodelled forecast — and this repo's whole point is that the rigour
claims are testable. Wiring the forecast leg in is a later, explicit step.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api.typing import Rolling
from pandas.tseries.holiday import USFederalHolidayCalendar

from features.panel import DEMAND_COLUMN, TEMPERATURE_COLUMN

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

    out[TARGET_COLUMN] = demand.reindex(target_col).to_numpy(dtype="float64")
    return out[list(DESIGN_COLUMNS)]


def feature_frame(design: pd.DataFrame) -> pd.DataFrame:
    """The model-facing view: features only, categoricals typed as such."""
    features = design[list(FEATURE_COLUMNS)].copy()
    for column in CATEGORICAL_FEATURES:
        features[column] = features[column].astype("int16")
    return features
