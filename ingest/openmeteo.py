"""Open-Meteo client — hourly 2 m temperature for the region's load centre.

No API key is required, which is why this leg of the pipeline is complete and
running today while the EIA leg waits for a key.

Two endpoints are stitched together, because neither covers the full range:

  * **ERA5 archive** (`archive-api`) — authoritative reanalysis, but it lags
    roughly 5 days behind now;
  * **forecast** (`api`, with `past_days`) — covers the recent tail plus the
    current day.

Overlap between the two is deliberate: the store de-duplicates on
``(site, timestamp_utc)`` keeping the newest pull, so the archive value wins
whenever it eventually becomes available.

A third endpoint, **historical forecast** (`historical-forecast-api`), serves
what the model *predicted* for a past hour rather than what happened. It feeds
a separate dataset — see `fetch_weather_forecast` — because a day-ahead
forecaster knows tomorrow's forecast, never tomorrow's weather, and mixing the
two in one table would let the reanalysis overwrite the forecast and turn an
honest feature into a perfect one.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime, timedelta

import httpx
import pandas as pd

from ingest.config import (
    OPEN_METEO_ARCHIVE_LAG_DAYS,
    OPEN_METEO_ARCHIVE_URL,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_HISTORICAL_FORECAST_URL,
    OPEN_METEO_MAX_PAST_DAYS,
    SLEEP_BETWEEN_PAGES,
)
from ingest.http import get_json

log = logging.getLogger(__name__)

HOURLY_VARIABLE = "temperature_2m"
ARCHIVE_CHUNK_DAYS = 365  # keep single responses to a sane size

COLUMNS = [
    "site",
    "timestamp_utc",
    "temperature_c",
    "is_observed",
    "source",
    "ingested_at_utc",
]

# --------------------------------------------------------------------------
# Archived forecasts
# --------------------------------------------------------------------------
# Weather drives load, but a day-ahead forecaster does not know tomorrow's
# weather — it knows tomorrow's *forecast*. These are the variables of that
# forecast, mapped from Open-Meteo's names to the lake's.
FORECAST_VARIABLES: dict[str, str] = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "dew_point_2m": "dewpoint_c",
    "wind_speed_10m": "wind_kmh",
    "cloud_cover": "cloud_pct",
}

# `_previous_day1` asks for the value as predicted by the model run of the day
# before — a lead of 24-48 h depending on the hour. A day-ahead operator running
# at 10:00 for tomorrow evening has a *fresher* run than this, so the feature
# understates what production would know. Understating is the safe direction:
# it can only make the measured skill pessimistic.
PREVIOUS_DAY_SUFFIX = "_previous_day1"

LEAD_PREVIOUS_DAY = "previous_day1"
LEAD_CURRENT_RUN = "current_run"

FORECAST_COLUMNS = [
    "site",
    "timestamp_utc",
    *FORECAST_VARIABLES.values(),
    "lead",
    "source",
    "ingested_at_utc",
]


def fetch_weather(
    client: httpx.Client,
    site: str,
    latitude: float,
    longitude: float,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Fetch hourly temperature in ``[start, end]`` (UTC) for one coordinate."""
    start_d = start.astimezone(UTC).date()
    end_d = end.astimezone(UTC).date()
    today = datetime.now(UTC).date()
    archive_end = min(end_d, today - timedelta(days=OPEN_METEO_ARCHIVE_LAG_DAYS))

    # Order matters: the store keeps the *last* row for a duplicated key, and
    # `sort_values` below is stable. Putting the archive after the recent pull
    # makes ERA5 reanalysis win over the forecast model wherever they overlap.
    frames: list[pd.DataFrame] = [
        _fetch_recent(client, site, latitude, longitude, start_d, archive_end, today)
    ]

    if start_d <= archive_end:
        frames.extend(_fetch_archive(client, site, latitude, longitude, start_d, archive_end))

    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    lo = pd.Timestamp(start)
    lo = lo.tz_localize("UTC") if lo.tzinfo is None else lo.tz_convert("UTC")
    df = df[df["timestamp_utc"] >= lo]
    return df.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)


def _fetch_archive(
    client: httpx.Client,
    site: str,
    latitude: float,
    longitude: float,
    start_d: date,
    end_d: date,
) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    chunk_start = start_d
    while chunk_start <= end_d:
        chunk_end = min(chunk_start + timedelta(days=ARCHIVE_CHUNK_DAYS - 1), end_d)
        log.info("Open-Meteo archive %s: %s -> %s", site, chunk_start, chunk_end)
        payload = get_json(
            client,
            OPEN_METEO_ARCHIVE_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "hourly": HOURLY_VARIABLE,
                "timezone": "UTC",
            },
            context=f"archive {chunk_start}..{chunk_end}",
        )
        frames.append(_to_frame(payload, site, "open_meteo_archive_era5"))
        chunk_start = chunk_end + timedelta(days=1)
        if chunk_start <= end_d:
            time.sleep(SLEEP_BETWEEN_PAGES)
    return frames


def _fetch_recent(
    client: httpx.Client,
    site: str,
    latitude: float,
    longitude: float,
    start_d: date,
    archive_end: date,
    today: date,
) -> pd.DataFrame:
    """Pull the tail the ERA5 archive has not caught up with yet."""
    # Start one day before the archive ended so the two windows overlap.
    tail_start = max(start_d, min(archive_end, today) - timedelta(days=1))
    past_days = (today - tail_start).days
    past_days = max(1, min(past_days, OPEN_METEO_MAX_PAST_DAYS))

    log.info("Open-Meteo recent %s: past_days=%d (+ today)", site, past_days)
    payload = get_json(
        client,
        OPEN_METEO_FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": HOURLY_VARIABLE,
            "past_days": past_days,
            "forecast_days": 1,
            "timezone": "UTC",
        },
        context=f"recent past_days={past_days}",
    )
    return _to_frame(payload, site, "open_meteo_forecast")


def _to_frame(payload: dict, site: str, source: str) -> pd.DataFrame:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    values = hourly.get(HOURLY_VARIABLE) or []

    if not times:
        return pd.DataFrame(columns=COLUMNS)

    now = pd.Timestamp.now(tz="UTC")
    ts = pd.to_datetime(pd.Series(times), utc=True)
    df = pd.DataFrame(
        {
            "site": site,
            "timestamp_utc": ts,
            "temperature_c": pd.to_numeric(pd.Series(values), errors="coerce"),
            # Hours in the future are model output, not observations. Flagging
            # them keeps "actuals" honest downstream.
            "is_observed": ts <= now,
            "source": source,
            "ingested_at_utc": now,
        }
    )
    return df.dropna(subset=["temperature_c"])[COLUMNS]


def fetch_weather_forecast(
    client: httpx.Client,
    site: str,
    latitude: float,
    longitude: float,
    start: datetime,
    end: datetime,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Fetch what the forecast *said*, hour by hour, for one coordinate.

    Two legs, mirroring `fetch_weather`, but neither of them ever returns an
    observation:

      * **archived forecast** — `_previous_day1` values from the historical
        forecast API, i.e. the day-before model run, for every hour up to
        yesterday. This is what training consumes;
      * **current run** — the live forecast, restricted to hours that have not
        happened yet. This is what serving consumes tomorrow morning.

    The archived leg is appended last, so wherever both cover an hour the
    day-ahead version wins and the stored history stays consistent with what
    the model was trained on.
    """
    now_ts = pd.Timestamp(now or datetime.now(UTC))
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    today = now_ts.date()

    start_d = start.astimezone(UTC).date()
    end_d = end.astimezone(UTC).date()

    frames: list[pd.DataFrame] = [_fetch_current_run(client, site, latitude, longitude, now_ts)]

    archive_end = min(end_d, today - timedelta(days=1))
    if start_d <= archive_end:
        frames.extend(
            _fetch_archived_forecast(client, site, latitude, longitude, start_d, archive_end)
        )

    present = [f for f in frames if not f.empty]
    if not present:
        return pd.DataFrame(columns=FORECAST_COLUMNS)

    df = pd.concat(present, ignore_index=True)
    lo = pd.Timestamp(start)
    lo = lo.tz_localize("UTC") if lo.tzinfo is None else lo.tz_convert("UTC")
    df = df[df["timestamp_utc"] >= lo]
    return df.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)


def _fetch_archived_forecast(
    client: httpx.Client,
    site: str,
    latitude: float,
    longitude: float,
    start_d: date,
    end_d: date,
) -> list[pd.DataFrame]:
    hourly = ",".join(f"{name}{PREVIOUS_DAY_SUFFIX}" for name in FORECAST_VARIABLES)
    frames: list[pd.DataFrame] = []
    chunk_start = start_d
    while chunk_start <= end_d:
        chunk_end = min(chunk_start + timedelta(days=ARCHIVE_CHUNK_DAYS - 1), end_d)
        log.info("Open-Meteo archived forecast %s: %s -> %s", site, chunk_start, chunk_end)
        payload = get_json(
            client,
            OPEN_METEO_HISTORICAL_FORECAST_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "hourly": hourly,
                "timezone": "UTC",
            },
            context=f"archived forecast {chunk_start}..{chunk_end}",
        )
        frames.append(
            _to_forecast_frame(
                payload,
                site,
                source="open_meteo_historical_forecast",
                lead=LEAD_PREVIOUS_DAY,
                suffix=PREVIOUS_DAY_SUFFIX,
            )
        )
        chunk_start = chunk_end + timedelta(days=1)
        if chunk_start <= end_d:
            time.sleep(SLEEP_BETWEEN_PAGES)
    return frames


def _fetch_current_run(
    client: httpx.Client,
    site: str,
    latitude: float,
    longitude: float,
    now_ts: pd.Timestamp,
) -> pd.DataFrame:
    """The live run, future hours only.

    Past hours are dropped deliberately. The current run's values for hours
    that already happened are near-analysis, not a day-ahead call, and letting
    them into the history would quietly make the training feature better than
    anything production could reproduce.
    """
    log.info("Open-Meteo current run %s: forecast_days=2", site)
    payload = get_json(
        client,
        OPEN_METEO_FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(FORECAST_VARIABLES),
            "forecast_days": 2,
            "timezone": "UTC",
        },
        context="current run forecast_days=2",
    )
    df = _to_forecast_frame(
        payload, site, source="open_meteo_forecast", lead=LEAD_CURRENT_RUN, suffix=""
    )
    return df[df["timestamp_utc"] > now_ts]


def _to_forecast_frame(
    payload: dict,
    site: str,
    source: str,
    lead: str,
    suffix: str,
) -> pd.DataFrame:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []

    if not times:
        return pd.DataFrame(columns=FORECAST_COLUMNS)

    df = pd.DataFrame(
        {
            "site": site,
            "timestamp_utc": pd.to_datetime(pd.Series(times), utc=True),
        }
    )
    for api_name, column in FORECAST_VARIABLES.items():
        values = hourly.get(f"{api_name}{suffix}") or [None] * len(times)
        df[column] = pd.to_numeric(pd.Series(values), errors="coerce")

    df["lead"] = lead
    df["source"] = source
    df["ingested_at_utc"] = pd.Timestamp.now(tz="UTC")
    # Temperature is the variable the features are built around; a row without
    # it carries nothing the model can use.
    return df.dropna(subset=["temperature_c"])[FORECAST_COLUMNS]


def default_window(
    last_stored: pd.Timestamp | None,
    backfill_days: int,
    revision_lookback: timedelta,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Full backfill on first run, otherwise the delta plus a revision tail."""
    now = now or datetime.now(UTC)
    if last_stored is None:
        return now - timedelta(days=backfill_days), now
    return last_stored.to_pydatetime() - revision_lookback, now
