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

import pandas as pd

from ingest.config import EIA_DEMAND, WEATHER_HOURLY
from ingest.store import read_dataset

DEMAND_COLUMN = "demand_mwh"
TEMPERATURE_COLUMN = "temperature_c"


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
    with_calendar: bool = True,
) -> pd.DataFrame:
    """Assemble the modelling panel from a demand series (+ optional weather)."""
    demand = to_hourly_grid(demand.rename(DEMAND_COLUMN))
    panel = demand.to_frame()

    if temperature is not None and not temperature.empty:
        # Left join on the demand grid: weather never extends the panel.
        panel[TEMPERATURE_COLUMN] = temperature.rename(TEMPERATURE_COLUMN).reindex(panel.index)

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
    }
