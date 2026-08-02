"""Walk-forward backtest — the evaluation protocol for every model in this repo.

Protocol
--------
The window is cut into daily **folds**. Each fold has a cutoff instant `T0`
(00:00 UTC by default). At that point the model may see the series up to, but
**strictly before**, `T0`; it forecasts horizons `h = 1..H` hours ahead, i.e.
the timestamps `T0 + h`. The cutoff then slides forward one day and the whole
thing repeats.

This is the part a random train/test split gets wrong on time series: a
shuffled split lets the model learn from Thursday to predict Wednesday. Here,
information only ever flows forward, and the slice handed to the model is built
by `_history_before` — a single place that enforces `index < cutoff`, on top of
the model's own assertion in `models.baseline.predict`.

Metrics are computed per horizon (a 1 h-ahead error and a 24 h-ahead error are
different problems) and pooled across folds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

DEFAULT_HORIZONS = tuple(range(1, 25))
DEFAULT_WEEKS = 8
# Fold boundary, UTC. Not arbitrary, and it was 00:00 until it was measured.
#
# `features.build.FORECAST_PUBLISHED_HOUR_UTC` treats the day-before model run
# covering a target day as published at midday. From a 00:00 origin, horizon 24
# is the only horizon whose target falls on the *next* calendar day, so it alone
# needed a run published at 12:00 that same day — twelve hours after the origin.
# It was correctly withheld, and horizon 24 was therefore scored with all seven
# `fcst_*` features NaN at every single origin.
#
# The cost was invisible on the fixture, where those features are worthless
# (the ablation there says they *hurt* by 0.59%), and severe on real demand,
# where they are worth 34%: MAE 10,982 at h24 against 2,820 averaged over
# h1-h23, of which -10,002 MWh was systematic bias.
#
# Moving the origin to midday is the fix that adds no information the forecaster
# would not have. The alternative — relaxing FORECAST_PUBLISHED_HOUR_UTC — would
# hand the model a run that had not been published yet, which is the leak this
# whole masking scheme exists to prevent. Midday is also the more honest
# simulation of a day-ahead desk, which decides before the market closes rather
# than at 20:00 the previous evening, local time.
#
# 12 is the earliest hour that works, and it works by an inclusive boundary
# (`published <= origin`). `test_every_backtest_horizon_can_actually_see_a_published_forecast`
# pins the relationship, so raising the publication hour without moving this
# fails loudly instead of quietly blinding a horizon again.
DEFAULT_CUTOFF_HOUR = 12


@dataclass
class BacktestResult:
    predictions: pd.DataFrame  # one row per (fold, horizon)
    by_horizon: pd.DataFrame
    overall: dict
    folds: list[pd.Timestamp] = field(default_factory=list)
    skipped_folds: int = 0
    warnings: list[str] = field(default_factory=list)


def _history_before(series: pd.Series, cutoff: pd.Timestamp) -> pd.Series:
    """The only slice a model is allowed to see for a fold at `cutoff`.

    Strictly `<`, never `<=`: the hour stamped `T0` is not complete at `T0`.
    """
    return series[series.index < cutoff]


def make_cutoffs(
    index: pd.DatetimeIndex,
    weeks: int,
    horizons: tuple[int, ...],
    cutoff_hour: int,
    min_history_hours: int,
) -> list[pd.Timestamp]:
    """Daily fold cutoffs over the last `weeks`, keeping folds fully evaluable.

    A cutoff is kept only when (a) enough history precedes it for the model to
    have something to read, and (b) the actuals for every horizon exist, so
    each horizon is scored on exactly the same set of folds.
    """
    if len(index) == 0:
        return []

    max_h = max(horizons)
    first_usable = index.min() + pd.Timedelta(hours=min_history_hours)
    last_usable = index.max() - pd.Timedelta(hours=max_h)

    # Start of the most recent `weeks` window, snapped to the cutoff hour.
    window_start = (index.max() - pd.Timedelta(weeks=weeks)).normalize() + pd.Timedelta(
        hours=cutoff_hour
    )
    start = max(window_start, first_usable.ceil("D") + pd.Timedelta(hours=cutoff_hour))

    if start > last_usable:
        return []

    return list(pd.date_range(start, last_usable, freq="D"))


def run(
    series: pd.Series,
    predict_fn,
    *,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    weeks: int = DEFAULT_WEEKS,
    cutoff_hour: int = DEFAULT_CUTOFF_HOUR,
    min_history_hours: int = 168,
) -> BacktestResult:
    """Run the walk-forward backtest.

    `predict_fn(history, target_times, cutoff) -> Series` is the model. It gets
    only the pre-cutoff history; anything it returns is treated as the forecast
    for `target_times`.
    """
    series = series.dropna().sort_index()
    horizons = tuple(sorted(horizons))
    cutoffs = make_cutoffs(series.index, weeks, horizons, cutoff_hour, min_history_hours)

    if not cutoffs:
        raise ValueError(
            "Not enough history for a walk-forward backtest: need at least "
            f"{min_history_hours}h of warm-up plus {weeks} week(s) of folds, "
            f"got {len(series)} hour(s)."
        )

    records: list[dict] = []
    used_folds: list[pd.Timestamp] = []
    skipped = 0
    warnings: list[str] = []

    for cutoff in cutoffs:
        history = _history_before(series, cutoff)
        if history.empty:
            skipped += 1
            continue

        target_times = pd.DatetimeIndex([cutoff + pd.Timedelta(hours=h) for h in horizons])
        preds = predict_fn(history, target_times, cutoff)
        actuals = series.reindex(target_times)

        fold_records = [
            {
                "cutoff_utc": cutoff,
                "horizon_h": h,
                "target_utc": t,
                "actual": actuals.loc[t],
                "prediction": preds.loc[t],
            }
            for h, t in zip(horizons, target_times, strict=True)
        ]

        usable = [r for r in fold_records if _is_scorable(r)]
        if len(usable) < len(fold_records):
            skipped += 1
            warnings.append(
                f"fold {cutoff.isoformat()}: "
                f"{len(fold_records) - len(usable)} horizon(s) unscorable (gaps in the series)"
            )
            continue

        records.extend(usable)
        used_folds.append(cutoff)

    if not records:
        raise ValueError("Every fold was unscorable — the series has too many gaps.")

    predictions = pd.DataFrame.from_records(records)
    predictions["error"] = predictions["prediction"] - predictions["actual"]
    predictions["abs_error"] = predictions["error"].abs()
    predictions["abs_pct_error"] = (predictions["abs_error"] / predictions["actual"].abs()) * 100.0

    by_horizon = (
        predictions.groupby("horizon_h")
        .agg(
            mae=("abs_error", "mean"),
            mape_pct=("abs_pct_error", "mean"),
            rmse=("error", lambda e: float(np.sqrt(np.mean(np.square(e))))),
            bias=("error", "mean"),
            n=("abs_error", "size"),
        )
        .reset_index()
    )

    overall = {
        "mae": float(predictions["abs_error"].mean()),
        "mape_pct": float(predictions["abs_pct_error"].mean()),
        "rmse": float(np.sqrt(np.mean(np.square(predictions["error"])))),
        "bias": float(predictions["error"].mean()),
        "n": len(predictions),
    }

    log.info(
        "Backtest: %d fold(s), %d horizon(s), MAE=%.1f MAPE=%.2f%%",
        len(used_folds),
        len(horizons),
        overall["mae"],
        overall["mape_pct"],
    )

    return BacktestResult(
        predictions=predictions,
        by_horizon=by_horizon,
        overall=overall,
        folds=used_folds,
        skipped_folds=skipped,
        warnings=warnings,
    )


def _is_scorable(record: dict) -> bool:
    actual, prediction = record["actual"], record["prediction"]
    if pd.isna(actual) or pd.isna(prediction):
        return False
    # MAPE is undefined at zero demand; such an hour is a data error anyway.
    return float(actual) != 0.0


def markdown_table(by_horizon: pd.DataFrame, every: int = 1) -> str:
    """Render the per-horizon table for the README / metrics artifact."""
    rows = by_horizon[by_horizon["horizon_h"] % every == 0] if every > 1 else by_horizon
    lines = [
        "| Horizon (h) | MAE (MWh) | MAPE (%) | RMSE (MWh) | Bias (MWh) | n |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows.itertuples(index=False):
        lines.append(
            f"| {int(row.horizon_h)} | {row.mae:,.0f} | {row.mape_pct:.2f} | "
            f"{row.rmse:,.0f} | {row.bias:+,.0f} | {int(row.n)} |"
        )
    return "\n".join(lines)
