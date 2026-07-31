"""Evaluate the shipped drift detectors against drift nobody designed.

Every drift result elsewhere in this repository is measured on a synthetic
series, and in two of the tests the shift is *injected by hand* — the detector
is asked to find a change the test author put there on purpose. That proves the
arithmetic works. It proves nothing about whether the thresholds are set
anywhere near right, because the size of the shift was chosen by the same person
who chose the threshold.

This script removes that circularity for the one leg of the pipeline that runs
on real data today: **hourly 2 m temperature for Philadelphia, from Open-Meteo's
ERA5 reanalysis.** No API key is needed, so this is reproducible by anyone.

The windows are picked by the calendar, not by inspecting the data:

    A  autumn -> winter        real regime change, should ALARM
    B  October -> October      same season a year apart, should stay OK
    C  October -> November     one month of real seasonal drift, the hard case
    D  first half -> second half of one October, should stay OK
    E  winter -> summer        the largest shift available, must ALARM
    F  January -> January      real interannual variation, small and real
    G  Oct 1-15, a year apart  a fortnight matched across years, should stay OK

B, D and G are the false-positive probes: nothing meaningful changed, so any
alarm there is the detector crying wolf. A and E are the true positives. C and F
are the cases that decide whether the thresholds are useful or merely loud — a
monitor that only fires between July and January is not monitoring anything.

F and G were added after A-E had been run, because A-E produced two clean true
positives and no misses, which is weak evidence when every shift in them is
enormous. That ordering is disclosed rather than smoothed over; see
`docs/DRIFT-EVALUATION.md`.

**This says nothing about the demand model.** Temperature is one input; the
demand series is still synthetic and every `metrics/*.json` still carries
`is_real: false`. What is evaluated here is the *detector*, on real data.

    uv run python scripts/drift_eval_real_weather.py

Writes `reports/_scan/real_weather_drift.json` and prints a markdown table.
The fetched series is cached under `reports/` (gitignored) so a re-run does not
hit the network again.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd

from drift import detectors
from drift.config import DEFAULT_THRESHOLDS
from ingest.config import WEATHER_LAT, WEATHER_LON, WEATHER_SITE
from ingest.openmeteo import fetch_weather

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "reports" / "_scan" / "real_weather.parquet"
OUT = REPO / "reports" / "_scan" / "real_weather_drift.json"

#: Pre-registered: written down before the numbers were seen, so the write-up
#: cannot be quietly reshaped around whatever the detector happened to say.
WINDOWS: list[dict] = [
    {
        "id": "A",
        "name": "autumn -> winter",
        "reference": ("2024-10-01", "2024-10-31"),
        "current": ("2025-01-01", "2025-01-31"),
        "expect": "alarm",
        "why": "a real seasonal regime change; the clearest true positive available",
    },
    {
        "id": "B",
        "name": "October -> October (a year apart)",
        "reference": ("2023-10-01", "2023-10-31"),
        "current": ("2024-10-01", "2024-10-31"),
        "expect": "quiet",
        "why": "same season, different year: weather varies but the regime does not",
    },
    {
        "id": "C",
        "name": "October -> November",
        "reference": ("2024-10-01", "2024-10-31"),
        "current": ("2024-11-01", "2024-11-30"),
        "expect": "unknown",
        "why": "one month of genuine seasonal drift -- the case that decides whether "
        "the thresholds are useful or merely loud",
    },
    {
        "id": "D",
        "name": "October first half -> second half",
        "reference": ("2024-10-01", "2024-10-15"),
        "current": ("2024-10-16", "2024-10-31"),
        "expect": "quiet",
        "why": "a fortnight apart inside one month: a false-positive probe",
    },
    {
        "id": "E",
        "name": "winter -> summer",
        "reference": ("2025-01-01", "2025-01-31"),
        "current": ("2024-07-01", "2024-07-31"),
        "expect": "alarm",
        "why": "the largest shift the calendar offers; failing here would be damning",
    },
    # -----------------------------------------------------------------------
    # Added in a second round, AFTER seeing A-E. Stated plainly rather than
    # folded in silently: A-E produced two clean true positives and no misses,
    # which is weak evidence, because every shift they contain is enormous. F
    # and G are small *real* changes -- the regime where a miss is possible.
    # Their expectations were written before they were run.
    # -----------------------------------------------------------------------
    {
        "id": "F",
        "name": "January -> January (a year apart)",
        "reference": ("2024-01-01", "2024-01-31"),
        "current": ("2025-01-01", "2025-01-31"),
        "expect": "unknown",
        "why": "real interannual variation: the same month in consecutive winters. "
        "Small, real, and the size of change a monitor would need to catch early",
    },
    {
        "id": "G",
        "name": "first half of October, a year apart",
        "reference": ("2023-10-01", "2023-10-15"),
        "current": ("2024-10-01", "2024-10-15"),
        "expect": "quiet",
        "why": "a fortnight matched across years: a second false-positive probe on "
        "a window the same size as D, holding the season fixed",
    },
]

FETCH_START = datetime(2023, 9, 1, tzinfo=UTC)
FETCH_END = datetime(2025, 2, 15, tzinfo=UTC)


def load_series() -> pd.DataFrame:
    """Real hourly temperature, cached locally after the first pull."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60.0) as client:
        frame = fetch_weather(
            client, WEATHER_SITE, WEATHER_LAT, WEATHER_LON, FETCH_START, FETCH_END
        )
    frame.to_parquet(CACHE, index=False)
    return frame


def slice_window(frame: pd.DataFrame, start: str, end: str) -> pd.Series:
    lo = pd.Timestamp(start, tz="UTC")
    hi = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    mask = (frame["timestamp_utc"] >= lo) & (frame["timestamp_utc"] < hi)
    return frame.loc[mask, "temperature_c"].astype("float64").reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    frame = load_series()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)

    results = []
    for spec in WINDOWS:
        reference = slice_window(frame, *spec["reference"])
        current = slice_window(frame, *spec["current"])

        column = detectors.compare_column(reference, current, "temperature_c", DEFAULT_THRESHOLDS)
        results.append(
            {
                **{k: spec[k] for k in ("id", "name", "expect", "why")},
                "reference": list(spec["reference"]),
                "current": list(spec["current"]),
                "reference_n": int(column["psi"]["reference_n"]),
                "current_n": int(column["psi"]["current_n"]),
                "reference_mean_c": round(float(reference.mean()), 2),
                "current_mean_c": round(float(current.mean()), 2),
                "mean_shift_c": round(float(current.mean() - reference.mean()), 2),
                "psi": round(float(column["psi"]["psi"]), 4),
                "ks_p": float(column["ks"]["p_value"]),
                "ks_significant": bool(column["ks"]["significant"]),
                "severity": column["severity"],
                "drift_detected": bool(column["drift_detected"]),
                "insufficient_data": bool(column["insufficient_data"]),
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "site": WEATHER_SITE,
                "source": "Open-Meteo ERA5 reanalysis (real observations)",
                "is_real": True,
                "note": (
                    "Real temperature data. This evaluates the DETECTOR only; the "
                    "demand model and every metrics/*.json remain synthetic."
                ),
                "thresholds": {
                    "psi_warn": DEFAULT_THRESHOLDS.psi_warn,
                    "psi_alert": DEFAULT_THRESHOLDS.psi_alert,
                    "ks_p_alert": DEFAULT_THRESHOLDS.ks_p_alert,
                    "min_samples": DEFAULT_THRESHOLDS.min_samples,
                },
                "windows": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    header = "| # | comparison | ref mean | cur mean | shift | PSI | KS p | verdict | expected |"
    print(header)
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        print(
            f"| {r['id']} | {r['name']} | {r['reference_mean_c']}°C | "
            f"{r['current_mean_c']}°C | {r['mean_shift_c']:+.2f}°C | {r['psi']} | "
            f"{r['ks_p']:.3g} | **{r['severity']}** | {r['expect']} |"
        )
    print(f"\nWrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
