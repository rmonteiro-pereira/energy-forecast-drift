"""`uv run python -m ingest` — pull the delta from every source into the lake.

Both legs are incremental and idempotent: the first run backfills
`HISTORY_YEARS` of hourly history, every later run pulls only what is missing
(plus a short revision tail) and merges it without creating duplicate
timestamps.

The EIA leg is skipped with a clear message while `EIA_API_KEY` is unset, so
the Open-Meteo leg still runs end to end. See docs/BLOCKED.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime

import httpx
import pandas as pd

from ingest import eia, openmeteo
from ingest.config import (
    BACKFILL_DAYS,
    BALANCING_AUTHORITY,
    DATA_DIR,
    EIA_DEMAND,
    INGEST_LEGS,
    REVISION_LOOKBACK,
    WEATHER_FORECAST_HOURLY,
    WEATHER_HOURLY,
    WEATHER_SITES,
    eia_api_key,
)
from ingest.http import ApiError
from ingest.store import last_timestamp, write_incremental

log = logging.getLogger("ingest")

USER_AGENT = "energy-forecast-drift/0.1 (portfolio project; contact via GitHub)"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__)
    parser.add_argument(
        "--source",
        choices=list(INGEST_LEGS),
        default="all",
        help="which leg to run (default: all)",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=BACKFILL_DAYS,
        help=f"history to pull on a first run (default: {BACKFILL_DAYS})",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="ignore what is already stored and re-pull the whole backfill window",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args(argv)


def ingest_eia(client: httpx.Client, args: argparse.Namespace) -> dict:
    if eia_api_key() is None:
        log.warning(
            "EIA_API_KEY not set -> skipping the demand leg. "
            "Register free at https://www.eia.gov/opendata/register.php, "
            "put EIA_API_KEY=... in .env and re-run. See docs/BLOCKED.md."
        )
        return {"status": "skipped", "reason": "missing_api_key"}

    respondent = eia.discover_respondent(client, BALANCING_AUTHORITY)
    stored = None if args.full_refresh else last_timestamp(EIA_DEMAND)
    start, end = eia.default_window(stored, args.backfill_days, REVISION_LOOKBACK)

    df = eia.fetch_demand(client, respondent["id"], start, end)
    report = write_incremental(EIA_DEMAND, df)
    return {
        "status": "ok",
        "respondent": respondent["id"],
        "respondent_name": respondent["name"],
        "window_utc": [start.isoformat(), end.isoformat()],
        **report.__dict__,
    }


def _weather_windows(args: argparse.Namespace, dataset) -> list[tuple]:
    """One delta window per site — a city added later still backfills fully."""
    windows = []
    for site in WEATHER_SITES:
        stored = None if args.full_refresh else last_timestamp(dataset, ("site", site.name))
        start, end = openmeteo.default_window(stored, args.backfill_days, REVISION_LOOKBACK)
        windows.append((site, start, end))
    return windows


def ingest_weather(client: httpx.Client, args: argparse.Namespace) -> dict:
    windows = _weather_windows(args, WEATHER_HOURLY)
    frames = [
        openmeteo.fetch_weather(client, site.name, site.latitude, site.longitude, start, end)
        for site, start, end in windows
    ]
    # One write for all sites rather than one per site: `write_incremental`
    # rewrites every partition it touches, and nine sequential writes would
    # rewrite the same two years of partitions nine times over.
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else None
    report = write_incremental(WEATHER_HOURLY, df if df is not None else pd.DataFrame())
    return {
        "status": "ok",
        "sites": [site.name for site, _, _ in windows],
        "window_utc": [windows[0][1].isoformat(), windows[0][2].isoformat()] if windows else None,
        **report.__dict__,
    }


def ingest_weather_forecast(client: httpx.Client, args: argparse.Namespace) -> dict:
    """The archived day-ahead forecast — what a forecaster knew, not what happened."""
    windows = _weather_windows(args, WEATHER_FORECAST_HOURLY)
    frames = [
        openmeteo.fetch_weather_forecast(
            client, site.name, site.latitude, site.longitude, start, end
        )
        for site, start, end in windows
    ]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else None
    report = write_incremental(WEATHER_FORECAST_HOURLY, df if df is not None else pd.DataFrame())
    return {
        "status": "ok",
        "sites": [site.name for site, _, _ in windows],
        "window_utc": [windows[0][1].isoformat(), windows[0][2].isoformat()] if windows else None,
        **report.__dict__,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Mixed on purpose: a top-level timestamp string plus one nested dict per
    # source leg, so the printed record is self-describing.
    summary: dict[str, object] = {"started_at_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    failures = 0

    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        legs = (
            ("eia", ingest_eia),
            ("weather", ingest_weather),
            ("weather_forecast", ingest_weather_forecast),
        )
        for name, fn in legs:
            if args.source not in ("all", name):
                continue
            try:
                summary[name] = fn(client, args)
            except (ApiError, eia.MissingApiKey) as exc:
                # Never let one source take the whole run down.
                log.error("%s ingestion failed: %s", name, exc)
                summary[name] = {"status": "error", "error": str(exc)}
                failures += 1

    print(json.dumps(summary, indent=2, default=str))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
