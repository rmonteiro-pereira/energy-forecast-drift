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
