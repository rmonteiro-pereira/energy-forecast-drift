"""EIA Open Data API v2 client — hourly electricity demand per balancing authority.

Route: ``/v2/electricity/rto/region-data`` with ``type=D`` (actual demand).
Periods are hourly and expressed in **UTC**, which is what lets us join the
series against Open-Meteo without a timezone dance.

The client is written to be fully functional the moment `EIA_API_KEY` lands in
`.env` — nothing here is stubbed. See docs/BLOCKED.md.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd

from ingest.config import (
    EIA_BASE_URL,
    EIA_PAGE_SIZE,
    SLEEP_BETWEEN_PAGES,
    eia_api_key,
)
from ingest.http import ApiError, get_json, redact_params

log = logging.getLogger(__name__)

ROUTE = "electricity/rto/region-data"
DEMAND_TYPE = "D"  # D = demand (actuals). DF = day-ahead forecast, NG = net gen.

# EIA formats hourly periods as YYYY-MM-DDTHH.
PERIOD_FORMAT = "%Y-%m-%dT%H"

# Paging safety net: 200 pages x 5000 rows = 1M hours, far beyond any sane pull.
MAX_PAGES = 200


class MissingApiKey(RuntimeError):
    """Raised when EIA data is requested but no API key is configured."""


def _key_or_raise() -> str:
    key = eia_api_key()
    if key is None:
        raise MissingApiKey(
            "EIA_API_KEY is not set. Register a free key at "
            "https://www.eia.gov/opendata/register.php and add it to .env. "
            "See docs/BLOCKED.md."
        )
    return key


def discover_respondent(client: httpx.Client, code: str) -> dict[str, str]:
    """Verify a balancing-authority code against the API's own facet listing.

    We never assume "PJM" is valid — we ask the API which respondents exist and
    fail loudly with suggestions if the configured code is not among them.
    """
    key = _key_or_raise()
    payload = get_json(
        client,
        f"{EIA_BASE_URL}/{ROUTE}/facet/respondent/",
        {"api_key": key},
        context="respondent discovery",
    )
    facets = payload.get("response", {}).get("facets", [])
    by_id = {str(f["id"]).upper(): str(f.get("name", "")) for f in facets}

    wanted = code.upper()
    if wanted not in by_id:
        near = sorted(rid for rid in by_id if wanted in rid or rid in wanted)
        raise ApiError(
            f"Balancing authority {code!r} is not a valid EIA respondent. "
            f"{len(by_id)} respondents available" + (f"; did you mean {near}?" if near else ".")
        )

    log.info("Resolved respondent %s -> %s", wanted, by_id[wanted])
    return {"id": wanted, "name": by_id[wanted]}


def fetch_demand(
    client: httpx.Client,
    respondent: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Fetch hourly demand in ``[start, end]`` (inclusive, UTC) as a tidy frame.

    Columns: ``respondent, timestamp_utc, demand_mwh, units, source, ingested_at_utc``.
    """
    key = _key_or_raise()
    start_str = start.astimezone(UTC).strftime(PERIOD_FORMAT)
    end_str = end.astimezone(UTC).strftime(PERIOD_FORMAT)

    base_params: dict[str, object] = {
        "api_key": key,
        "frequency": "hourly",
        "data[0]": "value",
        "facets[respondent][]": [respondent],
        "facets[type][]": [DEMAND_TYPE],
        "start": start_str,
        "end": end_str,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": EIA_PAGE_SIZE,
    }

    log.info(
        "EIA demand pull %s: %s -> %s (params=%s)",
        respondent,
        start_str,
        end_str,
        redact_params({k: v for k, v in base_params.items() if k != "api_key"}),
    )

    rows: list[dict] = []
    offset = 0
    total: int | None = None

    for page in range(MAX_PAGES):
        payload = get_json(
            client,
            f"{EIA_BASE_URL}/{ROUTE}/data/",
            {**base_params, "offset": offset},
            context=f"{respondent} page {page + 1}",
        )
        response = payload.get("response", {})
        batch = response.get("data", []) or []
        if total is None:
            total = int(response.get("total", 0) or 0)
            log.info("EIA reports %s hourly record(s) in range", total)

        rows.extend(batch)
        if len(batch) < EIA_PAGE_SIZE or len(rows) >= (total or 0):
            break

        offset += EIA_PAGE_SIZE
        # Politeness: never hammer the API in a tight loop.
        time.sleep(SLEEP_BETWEEN_PAGES)
    else:
        log.warning("Stopped paging at the %d-page safety cap", MAX_PAGES)

    return _to_frame(rows, respondent)


def _to_frame(rows: list[dict], respondent: str) -> pd.DataFrame:
    columns = [
        "respondent",
        "timestamp_utc",
        "demand_mwh",
        "units",
        "source",
        "ingested_at_utc",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    raw = pd.DataFrame(rows)
    df = pd.DataFrame(
        {
            "respondent": raw.get("respondent", respondent).astype(str),
            "timestamp_utc": pd.to_datetime(raw["period"], format=PERIOD_FORMAT, utc=True),
            # Always float: demand is a physical measure and must be able to
            # carry NaN for the hours the EIA has not published yet.
            "demand_mwh": pd.to_numeric(raw["value"], errors="coerce").astype("float64"),
            "units": raw.get("value-units", "megawatthours").astype(str),
        }
    )
    df["source"] = "eia_v2_region_data"
    df["ingested_at_utc"] = pd.Timestamp.now(tz="UTC")

    before = len(df)
    df = df.dropna(subset=["demand_mwh"])
    if len(df) < before:
        log.warning("Dropped %d EIA row(s) with a null demand value", before - len(df))

    return df[columns].sort_values("timestamp_utc").reset_index(drop=True)


def default_window(
    last_stored: pd.Timestamp | None,
    backfill_days: int,
    revision_lookback: timedelta,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Decide which window to pull: full backfill, or just the delta.

    When data already exists we restart `revision_lookback` before the newest
    stored hour, because the EIA revises recent values — re-pulling that tail
    lets the store overwrite stale numbers rather than keep them forever.
    """
    now = now or datetime.now(UTC)
    if last_stored is None:
        return now - timedelta(days=backfill_days), now
    start = last_stored.to_pydatetime() - revision_lookback
    return start, now
