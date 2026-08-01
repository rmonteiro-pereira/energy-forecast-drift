"""Turn the raw lake into a gapless hourly panel the models can consume.

The panel is the single contract between ingestion and modelling:

    timestamp_utc (index, hourly, no gaps) | demand_mwh | temperature_c | calendar...

Two properties matter for a time series pipeline and are enforced here rather
than assumed downstream:

  * **gapless** — the index is a complete hourly range, so "168 rows ago" and
    "168 hours ago" are the same thing. A missing hour becomes an explicit NaN
    instead of silently shifting every lag;
  * **no lookahead** — nothing in this module reads a future row. Calendar
    columns are functions of the timestamp alone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ingest.config import (
    EIA_DEMAND,
    SITE_WEIGHTS,
    WEATHER_FORECAST_HOURLY,
    WEATHER_HOURLY,
)
from ingest.store import read_dataset

DEMAND_COLUMN = "demand_mwh"
TEMPERATURE_COLUMN = "temperature_c"

# Columns the archived day-ahead forecast contributes to the panel. The `fcst_`
# prefix is load-bearing, not cosmetic: it is what separates "what the weather
# did" from "what the forecast said it would do", and every feature built on a
# `fcst_` column is allowed to be read at the *target* hour precisely because
# the value was published before the origin.
FORECAST_TEMPERATURE_COLUMN = "fcst_temperature_c"
FORECAST_SPREAD_COLUMN = "fcst_temperature_spread_c"
FORECAST_VALUE_COLUMNS = (
    FORECAST_TEMPERATURE_COLUMN,
    "fcst_humidity_pct",
    "fcst_dewpoint_c",
    "fcst_wind_kmh",
    "fcst_cloud_pct",
)
FORECAST_PANEL_COLUMNS = (*FORECAST_VALUE_COLUMNS, FORECAST_SPREAD_COLUMN)


def load_demand(respondent: str | None = None) -> pd.Series:
    """Hourly demand from the lake as a Series indexed by UTC timestamp."""
    df = read_dataset(EIA_DEMAND)
    if df.empty:
        return pd.Series(dtype="float64", name=DEMAND_COLUMN)
    if respondent is not None:
        df = df[df["respondent"].str.upper() == respondent.upper()]
    series = df.set_index("timestamp_utc")[DEMAND_COLUMN].sort_index()
    return series[~series.index.duplicated(keep="last")]


def load_temperature(site: str | None = None, observed_only: bool = True) -> pd.Series:
    """Hourly temperature from the lake as a Series indexed by UTC timestamp."""
    df = read_dataset(WEATHER_HOURLY)
    if df.empty:
        return pd.Series(dtype="float64", name=TEMPERATURE_COLUMN)
    if site is not None:
        df = df[df["site"] == site]
    if observed_only and "is_observed" in df.columns:
        # Drop forecast hours so the panel only ever contains actuals.
        df = df[df["is_observed"].astype(bool)]
    series = df.set_index("timestamp_utc")[TEMPERATURE_COLUMN].sort_index()
    return series[~series.index.duplicated(keep="last")]


def blend_by_site(
    df: pd.DataFrame,
    columns: tuple[str, ...],
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Population-weighted blend of per-site rows into one series per column.

    The weights are renormalised **per timestamp over the sites that actually
    reported**. Without that, an hour where Chicago is missing would come out
    colder or warmer purely because a third of the weight vanished, and the
    model would read a data gap as weather.
    """
    weights = SITE_WEIGHTS if weights is None else weights
    if df.empty:
        return pd.DataFrame(columns=list(columns))

    df = df.drop_duplicates(subset=["site", "timestamp_utc"], keep="last")
    ts = df["timestamp_utc"]
    # An unrecognised site contributes nothing rather than silently weighting 1.
    weight = df["site"].map(weights).astype("float64")

    out: dict[str, pd.Series] = {}
    for column in columns:
        if column not in df.columns:
            continue
        value = pd.to_numeric(df[column], errors="coerce")
        usable = value.notna() & weight.notna()
        numerator = (value.where(usable, 0.0) * weight.where(usable, 0.0)).groupby(ts).sum()
        denominator = weight.where(usable, 0.0).groupby(ts).sum()
        out[column] = numerator / denominator.replace(0.0, np.nan)

    if not out:
        return pd.DataFrame(columns=list(columns))
    blended = pd.DataFrame(out).sort_index()
    blended.index.name = "timestamp_utc"
    return blended


def site_spread(df: pd.DataFrame, column: str) -> pd.Series:
    """Max minus min across sites — how unevenly the weather sits on the footprint.

    A blended 18 °C can be 18 everywhere or 8 in Chicago and 28 in Richmond,
    and those two are not the same load. The blend alone cannot tell them apart.
    """
    if df.empty or column not in df.columns:
        return pd.Series(dtype="float64")
    value = pd.to_numeric(df[column], errors="coerce")
    grouped = value.groupby(df["timestamp_utc"])
    spread = grouped.max() - grouped.min()
    spread.index.name = "timestamp_utc"
    return spread.sort_index()


def load_temperature_blend() -> pd.Series:
    """Observed temperature, blended across every site in the lake."""
    df = read_dataset(WEATHER_HOURLY)
    if df.empty:
        return pd.Series(dtype="float64", name=TEMPERATURE_COLUMN)
    if "is_observed" in df.columns:
        df = df[df["is_observed"].astype(bool)]
    blended = blend_by_site(df, (TEMPERATURE_COLUMN,))
    if TEMPERATURE_COLUMN not in blended.columns:
        return pd.Series(dtype="float64", name=TEMPERATURE_COLUMN)
    return blended[TEMPERATURE_COLUMN].rename(TEMPERATURE_COLUMN)


def load_weather_forecast() -> pd.DataFrame:
    """The archived day-ahead forecast, blended across sites, one row per hour.

    Indexed by the hour the forecast is **valid for**, not the hour it was made.
    Deciding whether a given row was already published at a given origin is the
    feature builder's job — see `features.build.FORECAST_PUBLISHED_HOUR_UTC`.
    """
    df = read_dataset(WEATHER_FORECAST_HOURLY)
    if df.empty:
        return pd.DataFrame(columns=list(FORECAST_PANEL_COLUMNS))

    raw = {
        "temperature_c": FORECAST_TEMPERATURE_COLUMN,
        "humidity_pct": "fcst_humidity_pct",
        "dewpoint_c": "fcst_dewpoint_c",
        "wind_kmh": "fcst_wind_kmh",
        "cloud_pct": "fcst_cloud_pct",
    }
    present = {source: target for source, target in raw.items() if source in df.columns}
    blended = blend_by_site(df, tuple(present)).rename(columns=present)
    blended[FORECAST_SPREAD_COLUMN] = site_spread(df, "temperature_c")
    return blended.reindex(columns=list(FORECAST_PANEL_COLUMNS))


def to_hourly_grid(series: pd.Series) -> pd.Series:
    """Reindex onto a complete hourly range; missing hours become NaN."""
    if series.empty:
        return series
    full = pd.date_range(series.index.min(), series.index.max(), freq="h", tz="UTC")
    return series.reindex(full)


def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar features derived purely from the index — no lookahead possible."""
    # Stated rather than assumed. Every caller passes an hourly UTC panel, and
    # `.hour` / `.dayofweek` silently do not exist on a plain Index — so a
    # mis-indexed frame would fail here with an AttributeError several frames
    # from the cause. It also gives the type checker the narrowing it needs.
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError(
            f"add_calendar() needs a DatetimeIndex, got {type(df.index).__name__}. "
            "Build the panel with build_panel() first."
        )
    idx: pd.DatetimeIndex = df.index
    return df.assign(
        hour=idx.hour,
        dayofweek=idx.dayofweek,
        month=idx.month,
        is_weekend=(idx.dayofweek >= 5).astype(int),
    )


def build_panel(
    demand: pd.Series,
    temperature: pd.Series | None = None,
    forecast: pd.DataFrame | None = None,
    with_calendar: bool = True,
) -> pd.DataFrame:
    """Assemble the modelling panel from a demand series (+ optional weather).

    `forecast` carries the `fcst_` columns from `load_weather_forecast`. It is
    optional for the same reason `temperature` is: the panel schema has to stay
    stable when a leg of ingestion has not run, so downstream code sees NaN
    rather than a missing column.
    """
    demand = to_hourly_grid(demand.rename(DEMAND_COLUMN))
    panel = demand.to_frame()

    if temperature is not None and not temperature.empty:
        # Left join on the demand grid: weather never extends the panel.
        panel[TEMPERATURE_COLUMN] = temperature.rename(TEMPERATURE_COLUMN).reindex(panel.index)

    if forecast is not None and not forecast.empty:
        for column in FORECAST_PANEL_COLUMNS:
            if column in forecast.columns:
                panel[column] = pd.to_numeric(forecast[column], errors="coerce").reindex(
                    panel.index
                )

    panel.index.name = "timestamp_utc"
    return add_calendar(panel) if with_calendar else panel


def describe_panel(panel: pd.DataFrame) -> dict:
    """Small summary used in the metrics artifact and the run log."""
    demand = panel[DEMAND_COLUMN]
    return {
        "rows": len(panel),
        "start_utc": panel.index.min().isoformat() if len(panel) else None,
        "end_utc": panel.index.max().isoformat() if len(panel) else None,
        "missing_demand_hours": int(demand.isna().sum()),
        "has_temperature": TEMPERATURE_COLUMN in panel.columns,
        "has_weather_forecast": FORECAST_TEMPERATURE_COLUMN in panel.columns,
    }
