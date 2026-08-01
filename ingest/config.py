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

# The legs `python -m ingest` can run, named once. `pipeline.daily` forwards its
# own `--ingest-source` straight through, and the two lists drifting apart is a
# silent failure: the daily job simply stops being able to ask for a leg that
# exists. `tests/test_pipeline_daily.py` holds them together.
INGEST_LEGS = ("all", "eia", "weather", "weather_forecast")

# Representative coordinate for the weather series. PJM's load centre of
# gravity sits between Philadelphia and Baltimore; we use Philadelphia, PA.
# Kept as the *reference* site: it is the one the single-site era used, so
# artifacts and docs that name a site keep naming the same one.
WEATHER_SITE = "philadelphia_pa"
WEATHER_LAT = 39.9526
WEATHER_LON = -75.1652


@dataclass(frozen=True)
class WeatherSite:
    """One weather sampling point in the PJM footprint, with its blend weight."""

    name: str
    latitude: float
    longitude: float
    # Metro-area population in millions.
    #
    # This is a PROXY for the site's share of PJM load, not a PJM figure. PJM
    # does publish zonal peak loads, and using them would be strictly better;
    # population is used here because it is public, stable and checkable
    # without a licence, and because load per capita varies far less across
    # these metros than population does. Treat the weights as approximate:
    # they decide how much each city pulls the blended temperature, and a
    # 20% error in one weight moves the blend by a fraction of a degree.
    weight_millions: float


# One city was never enough. PJM spans ~13 states and ~65 million people, and a
# single point in Philadelphia cannot see a heat wave sitting over Chicago —
# which is the largest single load zone in the footprint (ComEd). These nine
# metros cover the large zones; the blend is population-weighted.
WEATHER_SITES: tuple[WeatherSite, ...] = (
    WeatherSite("chicago_il", 41.8781, -87.6298, 9.4),  # ComEd
    WeatherSite("washington_dc", 38.9072, -77.0369, 6.3),  # Pepco + Dominion north
    WeatherSite("philadelphia_pa", 39.9526, -75.1652, 6.2),  # PECO
    WeatherSite("baltimore_md", 39.2904, -76.6122, 2.8),  # BGE
    WeatherSite("newark_nj", 40.7357, -74.1724, 2.5),  # PSEG — northern NJ only
    WeatherSite("pittsburgh_pa", 40.4406, -79.9959, 2.4),  # Duquesne + APS
    WeatherSite("cleveland_oh", 41.4993, -81.6944, 2.1),  # ATSI
    WeatherSite("columbus_oh", 39.9612, -82.9988, 2.1),  # AEP Ohio
    WeatherSite("richmond_va", 37.5407, -77.4360, 1.3),  # Dominion south
)

SITE_WEIGHTS: dict[str, float] = {
    site.name: site.weight_millions / sum(s.weight_millions for s in WEATHER_SITES)
    for site in WEATHER_SITES
}

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

# Archived FORECASTS — what the model said at the time, not what happened.
#
# This is the endpoint that makes forward-looking weather honest. The ERA5
# archive above answers "how warm was it?"; this one answers "how warm did we
# think it would be, a day before?". Those differ by roughly 1.5 °C, and that
# gap is exactly the uncertainty a real day-ahead forecaster carries. Training
# on the reanalysis and serving on a forecast would hide it.
OPEN_METEO_HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"


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

# Deliberately a SEPARATE dataset from `weather_hourly` rather than extra
# columns on it. The two are keyed the same way, and `write_incremental` keeps
# the newest row for a key — so if forecasts lived alongside observations, the
# ERA5 reanalysis would overwrite the forecast the moment it caught up, and the
# feature would silently turn into a perfect forecast. Separation is what makes
# that failure impossible rather than merely unlikely.
WEATHER_FORECAST_HOURLY = Dataset(
    name="weather_forecast_hourly",
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
