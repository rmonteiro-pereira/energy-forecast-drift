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

from ingest import eia, openmeteo
from ingest.config import (
    BACKFILL_DAYS,
    BALANCING_AUTHORITY,
    DATA_DIR,
    EIA_DEMAND,
    REVISION_LOOKBACK,
    WEATHER_HOURLY,
    WEATHER_LAT,
    WEATHER_LON,
    WEATHER_SITE,
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
        choices=["all", "eia", "weather"],
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


def ingest_weather(client: httpx.Client, args: argparse.Namespace) -> dict:
    stored = None if args.full_refresh else last_timestamp(WEATHER_HOURLY)
    start, end = openmeteo.default_window(stored, args.backfill_days, REVISION_LOOKBACK)

    df = openmeteo.fetch_weather(client, WEATHER_SITE, WEATHER_LAT, WEATHER_LON, start, end)
    report = write_incremental(WEATHER_HOURLY, df)
    return {
        "status": "ok",
        "site": WEATHER_SITE,
        "window_utc": [start.isoformat(), end.isoformat()],
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
        for name, fn in (("eia", ingest_eia), ("weather", ingest_weather)):
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
