"""SYNTHETIC demand fixture — a stand-in while the EIA API key is pending.

WHY THIS EXISTS
---------------
The EIA key had not been registered when M0/M1 were built (docs/BLOCKED.md), so
there is no real demand history yet. Rather than ship a backtest nobody can
run, the pipeline can be driven by a deterministic synthetic series. It makes
the code executable and testable *today*.

WHAT IT IS NOT
--------------
It is **not** data and the MAE it produces is **not** a result. It is a
plausible-looking curve from a seeded random generator, and every artifact
derived from it is stamped `"is_real": false`. The real baseline number gets
recomputed — and this fixture retired — the moment the key lands.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 20260728
SYNTHETIC_LABEL = "SYNTHETIC — NOT REAL DATA"

# The fixture ends at a fixed instant rather than "now" on purpose: a window
# that slid with the wall clock would rewrite metrics/baseline.json on every
# run, churning a committed artifact for no reason. Anchored, the whole
# pipeline is byte-reproducible until real data replaces it.
ANCHOR_END = pd.Timestamp("2026-07-28T00:00", tz="UTC")

# Loosely PJM-shaped (tens of GW) so plots look sane. Not calibrated to
# anything; do not read meaning into these constants.
BASE_MW = 95_000.0
DAILY_AMPLITUDE = 18_000.0
EVENING_PEAK = 7_000.0
WEEKEND_DROP = 8_000.0
ANNUAL_AMPLITUDE = 12_000.0
TEMP_SENSITIVITY = 900.0  # MW per degree away from the comfort point
COMFORT_C = 18.0
NOISE_SD = 2_200.0


def synthetic_demand(
    start: pd.Timestamp,
    end: pd.Timestamp,
    seed: int = SEED,
) -> pd.DataFrame:
    """Deterministic hourly demand + temperature over ``[start, end]`` (UTC).

    Same arguments always give the same series, so backtest numbers computed
    from it are reproducible (and reproducibly meaningless as a benchmark).
    """
    index = pd.date_range(start, end, freq="h", tz="UTC")
    rng = np.random.default_rng(seed)

    hour = index.hour.to_numpy()
    dow = index.dayofweek.to_numpy()
    doy = index.dayofyear.to_numpy()

    # Annual temperature cycle (northern hemisphere) + weather noise.
    seasonal_temp = 12.5 - 13.0 * np.cos(2 * np.pi * (doy - 15) / 365.25)
    diurnal_temp = 4.5 * np.sin(2 * np.pi * (hour - 9) / 24)
    weather_noise = rng.normal(0.0, 2.0, size=len(index)).cumsum() * 0.05
    temperature = seasonal_temp + diurnal_temp + weather_noise

    # Load shape: morning ramp, evening peak, weekend drop.
    daily = -DAILY_AMPLITUDE * np.cos(2 * np.pi * (hour - 4) / 24)
    # Circular distance to 19:00 so the peak is symmetric across midnight.
    hours_to_peak = np.minimum((hour - 19) % 24, (19 - hour) % 24)
    evening = EVENING_PEAK * np.exp(-(hours_to_peak**2) / 6.0)
    weekend = np.where(dow >= 5, -WEEKEND_DROP, 0.0)
    annual = -ANNUAL_AMPLITUDE * np.cos(2 * np.pi * (doy - 200) / 365.25)

    # V-shaped temperature response: heating below comfort, cooling above.
    thermal = TEMP_SENSITIVITY * np.abs(temperature - COMFORT_C)

    demand = (
        BASE_MW
        + daily
        + evening
        + weekend
        + annual
        + thermal
        + rng.normal(0.0, NOISE_SD, size=len(index))
    )

    return pd.DataFrame(
        {
            "demand_mwh": demand.round(1),
            "temperature_c": temperature.round(2),
        },
        index=index,
    ).rename_axis("timestamp_utc")


def synthetic_series(
    end: pd.Timestamp | None = None,
    days: int = 200,
    seed: int = SEED,
) -> pd.DataFrame:
    """`days` of history ending at `end` (default: the fixed `ANCHOR_END`)."""
    end = (end or ANCHOR_END).floor("h")
    return synthetic_demand(end - pd.Timedelta(days=days), end, seed=seed)


# A day-ahead forecast is wrong by about this much. Measured, not guessed:
# Open-Meteo's day-before run differs from its own reanalysis by ~1.5 °C MAE
# over Philadelphia and Chicago. The fixture reproduces that error so the
# synthetic path exercises the same feature set as the real one — including the
# fact that forecast temperature is *not* the temperature.
FORECAST_ERROR_SD_C = 1.5


def synthetic_forecast(frame: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """A plausible archived day-ahead forecast for a synthetic history.

    Same disclaimer as everything else in this module: not data. It exists so
    `--source synthetic` produces the full design matrix instead of a truncated
    one, which is what keeps the schema testable while the real lake fills.
    """
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError(
            f"synthetic_forecast() needs the hourly frame from synthetic_series(), "
            f"got an index of type {type(frame.index).__name__}."
        )
    index: pd.DatetimeIndex = frame.index
    rng = np.random.default_rng(seed + 1)
    truth = frame["temperature_c"].to_numpy(dtype="float64")

    error = rng.normal(0.0, FORECAST_ERROR_SD_C, size=len(index))
    forecast = truth + error

    hour = index.hour.to_numpy()
    return pd.DataFrame(
        {
            "fcst_temperature_c": forecast.round(2),
            # Anti-correlated with temperature, as humidity broadly is.
            "fcst_humidity_pct": np.clip(
                80.0 - 1.2 * (forecast - COMFORT_C) + rng.normal(0.0, 6.0, len(index)), 5.0, 100.0
            ).round(1),
            "fcst_dewpoint_c": (
                forecast - np.clip(rng.normal(6.0, 2.5, len(index)), 0.5, None)
            ).round(2),
            "fcst_wind_kmh": np.clip(rng.gamma(2.0, 6.0, len(index)), 0.0, None).round(1),
            "fcst_cloud_pct": np.clip(rng.beta(1.4, 1.4, len(index)) * 100.0, 0.0, 100.0).round(1),
            # Sites disagree more in winter and at night; the shape matters more
            # than the magnitude for a smoke test.
            "fcst_temperature_spread_c": np.abs(
                6.0 + 2.0 * np.cos(2 * np.pi * (hour - 6) / 24) + rng.normal(0.0, 1.0, len(index))
            ).round(2),
        },
        index=index,
    ).rename_axis("timestamp_utc")
