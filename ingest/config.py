"""Central configuration for the ingestion layer.

Every tunable lives here so the rest of the code has no magic constants.
Secrets are read from the environment (loaded from `.env` if present) and are
never logged, printed or persisted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# `.env` is gitignored; load it if the developer has one.
load_dotenv(override=False)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
METRICS_DIR = REPO_ROOT / "metrics"

# ---------------------------------------------------------------------------
# Region under study
# ---------------------------------------------------------------------------
# PJM Interconnection: ~65 GW peak, 13 states, strong daily + weekly + seasonal
# cycles and a heavy temperature response -> the best EIA respondent to make
# drift visible. The respondent code is *verified* against the API's facet
# endpoint by `ingest.eia.discover_respondent`, never hardcoded blindly.
BALANCING_AUTHORITY = os.getenv("BALANCING_AUTHORITY", "PJM")

# Representative coordinate for the weather series. PJM's load centre of
# gravity sits between Philadelphia and Baltimore; we use Philadelphia, PA.
WEATHER_SITE = "philadelphia_pa"
WEATHER_LAT = 39.9526
WEATHER_LON = -75.1652

# ---------------------------------------------------------------------------
# History window
# ---------------------------------------------------------------------------
# Spec asks for "at least 2 years" of hourly history on the first full pull.
HISTORY_YEARS = int(os.getenv("HISTORY_YEARS", "2"))
BACKFILL_DAYS = HISTORY_YEARS * 365

# EIA publishes ~2x/day and revises recent hours. We always re-pull a short
# tail so revisions overwrite the values we already stored.
REVISION_LOOKBACK = timedelta(days=int(os.getenv("REVISION_LOOKBACK_DAYS", "3")))

# ---------------------------------------------------------------------------
# HTTP politeness (see ingest.http)
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0  # 2s, 4s, 8s
SLEEP_BETWEEN_PAGES = 0.5  # never hammer an API in a tight loop
REQUEST_TIMEOUT = 60.0

# EIA hard-caps a single response at 5000 rows.
EIA_PAGE_SIZE = 5000
EIA_BASE_URL = "https://api.eia.gov/v2"

# Open-Meteo: ERA5 archive lags ~5 days; the forecast endpoint serves the
# recent tail via `past_days`. We stitch the two.
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_LAG_DAYS = 6
OPEN_METEO_MAX_PAST_DAYS = 92  # API limit for `past_days` on the forecast route


@dataclass(frozen=True)
class Dataset:
    """Describes one parquet dataset in the local lake."""

    name: str
    # Columns that uniquely identify a row. Re-ingesting the same key
    # overwrites instead of duplicating -> idempotency.
    key_columns: tuple[str, ...]
    time_column: str

    @property
    def path(self) -> Path:
        return DATA_DIR / "raw" / self.name


EIA_DEMAND = Dataset(
    name="eia_demand",
    key_columns=("respondent", "timestamp_utc"),
    time_column="timestamp_utc",
)

WEATHER_HOURLY = Dataset(
    name="weather_hourly",
    key_columns=("site", "timestamp_utc"),
    time_column="timestamp_utc",
)


def eia_api_key() -> str | None:
    """Return the EIA API key, or None when it has not been configured yet.

    Callers must degrade gracefully: at the time of writing the key had not
    been registered, so `ingest` skips the EIA leg with a clear message
    instead of failing. See docs/BLOCKED.md.
    """
    key = os.getenv("EIA_API_KEY", "").strip()
    return key or None
