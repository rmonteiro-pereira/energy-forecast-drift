"""The two charts the daily run leaves behind.

They exist so that a bad day is visible without opening a JSON file: the
forecast-vs-actual panel shows *where* the model was wrong, the rolling-MAE
panel shows *when* it started being wrong. The React dashboard (M6) reads the
JSON; these PNGs are what survives in a commit diff and in the README.

Matplotlib is forced onto the `Agg` backend at import time — the daily job runs
headless on a GitHub runner, and the default backend probe is a slow way to
discover there is no display.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

log = logging.getLogger(__name__)

# A colour-blind-safe trio: actual, forecast, alert.
ACTUAL = "#1b3a5c"
FORECAST = "#e07a2f"
ALERT = "#c1352b"
GRID = "#d8dde3"

SYNTHETIC_BANNER = "SYNTHETIC FIXTURE — NOT REAL DATA"


def _style(ax) -> None:
    ax.grid(True, color=GRID, linewidth=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _stamp_if_synthetic(fig, is_real: bool) -> None:
    """A watermark, not a footnote. A screenshot has to carry its own caveat."""
    if is_real:
        return
    fig.text(
        0.5,
        0.5,
        SYNTHETIC_BANNER,
        fontsize=26,
        color=ALERT,
        alpha=0.13,
        ha="center",
        va="center",
        rotation=18,
        weight="bold",
        zorder=10,
    )


def forecast_vs_actual(
    frame: pd.DataFrame,
    path: Path,
    *,
    is_real: bool,
    title: str = "Forecast vs actual — most recent days",
) -> Path:
    """`frame` needs `target_utc`, `actual_mwh` and `forecast_mwh` columns."""
    fig, (ax, ax_err) = plt.subplots(
        2, 1, figsize=(11, 6.5), sharex=True, height_ratios=[3, 1], constrained_layout=True
    )

    times = pd.DatetimeIndex(frame["target_utc"])
    ax.plot(times, frame["actual_mwh"], color=ACTUAL, linewidth=1.9, label="actual")
    ax.plot(
        times,
        frame["forecast_mwh"],
        color=FORECAST,
        linewidth=1.6,
        linestyle="--",
        label="forecast",
    )
    ax.fill_between(
        times,
        frame["actual_mwh"],
        frame["forecast_mwh"],
        color=FORECAST,
        alpha=0.14,
        label="error",
    )
    ax.set_ylabel("demand (MWh)")
    ax.set_title(title, loc="left", fontsize=12, weight="bold")
    ax.legend(loc="upper left", frameon=False, ncol=3)
    _style(ax)

    errors = frame["forecast_mwh"] - frame["actual_mwh"]
    ax_err.axhline(0.0, color=ACTUAL, linewidth=1.0)
    ax_err.fill_between(times, 0.0, errors, color=ALERT, alpha=0.45)
    ax_err.set_ylabel("error (MWh)")
    ax_err.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    _style(ax_err)

    _stamp_if_synthetic(fig, is_real)
    return _save(fig, path)


def rolling_mae(
    daily: pd.DataFrame,
    path: Path,
    *,
    is_real: bool,
    reference_mae: float | None = None,
    alert_ratio: float | None = None,
    title: str = "Rolling forecast error — the drift monitor",
) -> Path:
    """`daily` needs `day_utc`, `mae` and `mae_rolling`; `window` shades the split."""
    fig, ax = plt.subplots(figsize=(11, 4.6), constrained_layout=True)
    days = pd.DatetimeIndex(daily["day_utc"])

    ax.bar(days, daily["mae"], color=ACTUAL, alpha=0.28, width=0.85, label="daily MAE")
    ax.plot(days, daily["mae_rolling"], color=FORECAST, linewidth=2.2, label="rolling mean")

    if reference_mae is not None:
        ax.axhline(
            reference_mae,
            color=ACTUAL,
            linestyle=":",
            linewidth=1.6,
            label=f"reference MAE ({reference_mae:,.0f})",
        )
        if alert_ratio is not None:
            line = reference_mae * (1.0 + alert_ratio)
            ax.axhline(
                line,
                color=ALERT,
                linestyle="--",
                linewidth=1.6,
                label=f"retrain line (+{alert_ratio:.0%})",
            )

    if "window" in daily.columns:
        current = daily[daily["window"] == "current"]
        if not current.empty:
            ax.axvspan(
                pd.Timestamp(current["day_utc"].iloc[0]),
                pd.Timestamp(current["day_utc"].iloc[-1]),
                color=FORECAST,
                alpha=0.07,
            )

    ax.set_ylabel("MAE (MWh)")
    ax.set_title(title, loc="left", fontsize=12, weight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.legend(loc="upper left", frameon=False, ncol=2, fontsize=9)
    _style(ax)

    _stamp_if_synthetic(fig, is_real)
    return _save(fig, path)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    log.info("wrote %s", path)
    return path
