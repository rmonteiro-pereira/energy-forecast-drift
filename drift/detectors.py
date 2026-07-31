"""The four drift types, each producing one section of `metrics/drift.json`.

They are genuinely different failure modes and a monitor that only implements
one of them is the usual mistake:

* **feature drift** — the inputs moved. Leading indicator; the model may still
  be fine, because it may not lean on the column that moved.
* **target drift** — the thing being predicted moved. A new demand regime
  (a heatwave, a new large load on the grid) that the model has never fitted.
* **prediction drift** — the model's *output* distribution moved. This is the
  one you can compute with **no labels at all**, which matters here because the
  actual demand for the last hour arrives with a lag. It is the earliest signal
  available in production.
* **performance drift** — the errors got worse. The only signal that proves
  harm; also the slowest, because it has to wait for the actuals.

The first three are distribution comparisons and share the same machinery
(`drift.stats`: PSI as the headline, KS as a second opinion). The fourth is a
rolling error comparison and has its own shape.

Every section reports `severity` (`ok` / `warn` / `alert`), the numbers behind
it, and the thresholds that were applied — so the artifact explains its own
verdict without anyone re-reading this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from drift import stats
from drift.config import DEFAULT_THRESHOLDS, DriftThresholds, Severity
from drift.windows import (
    ABS_ERROR_COLUMN,
    ABS_PCT_ERROR_COLUMN,
    ERROR_COLUMN,
    PREDICTION_COLUMN,
    ScoredWindows,
)
from features import build as build_mod

INSUFFICIENT_DATA = "insufficient_data"

# Columns that are functions of the timestamp (or of the design grid) rather
# than of anything observed. Their PSI is still computed and reported — it is
# useful for sanity-checking the window geometry — but it is **excluded from the
# section verdict**, because it measures the calendar, not the data.
#
# Concretely: a 28-day reference window and a 14-day current window necessarily
# cover different months, so `month` has a PSI of ~7 on every healthy run, and
# `is_holiday` swings on whether either window happened to contain a holiday.
# Letting those drive the alarm would mean the feature-drift signal fires every
# single day and therefore means nothing.
DETERMINISTIC_COLUMNS = frozenset({*build_mod.CALENDAR_FEATURES, "horizon_h"})


@dataclass
class DriftSection:
    """One drift type's verdict plus the evidence for it."""

    drift_type: str
    severity: Severity
    summary: str
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "drift_type": self.drift_type,
            "severity": self.severity.value,
            "drift_detected": self.severity is not Severity.OK,
            "summary": self.summary,
            **self.details,
        }


# ---------------------------------------------------------------------------
# shared: one column, two windows
# ---------------------------------------------------------------------------
def compare_column(
    reference,
    current,
    name: str,
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
    with_bins: bool = False,
) -> dict:
    """PSI + KS + distribution summary for a single column.

    The severity is driven by PSI. The KS p-value is recorded and can *raise*
    an `ok` to a `warn`, but never to an `alert` on its own: with thousands of
    rows KS rejects the null for shifts far too small to matter to a
    forecaster, so letting it alert would mean alerting every day.
    """
    psi = stats.population_stability_index(
        reference,
        current,
        bins=thresholds.psi_bins,
        max_categorical_levels=thresholds.max_categorical_levels,
    )
    ks = stats.ks_two_sample(reference, current)

    severity = thresholds.psi_severity(psi.psi)
    ks_significant = ks.p_value < thresholds.ks_p_alert
    if ks_significant and severity is Severity.OK:
        severity = Severity.WARN

    insufficient = min(psi.reference_n, psi.current_n) < thresholds.min_samples
    if insufficient:
        severity = Severity.OK

    return {
        "column": name,
        "severity": severity.value,
        "drift_detected": severity is not Severity.OK,
        "insufficient_data": insufficient,
        "deterministic": name in DETERMINISTIC_COLUMNS,
        "psi": psi.as_dict(with_detail=with_bins),
        "ks": {**ks.as_dict(), "significant": ks_significant},
        "distribution": stats.summarise(reference, current),
    }


def _section_from_columns(
    drift_type: str,
    columns: list[dict],
    thresholds: DriftThresholds,
) -> tuple[Severity, dict]:
    """Roll per-column verdicts into a section verdict.

    A single alerting column out of twenty is a note, not an emergency, so the
    section escalates on the *share* of drifted columns — except for
    single-column sections (target, prediction) where the share is the column.

    Deterministic calendar columns are dropped here (see `DETERMINISTIC_COLUMNS`):
    they are reported in `columns` but never vote.
    """
    scored = [
        c for c in columns if not c["insufficient_data"] and not c.get("deterministic", False)
    ]
    if not scored:
        return Severity.OK, {
            "columns_scored": 0,
            # Reported on this branch too, not only the scored one. A consumer
            # should not have to discover that the artifact's key set depends on
            # whether anything happened to be eligible -- and "everything was
            # excluded as deterministic" is precisely when a reader most wants
            # to know *which* columns those were.
            "columns_excluded_deterministic": sorted(
                c["column"] for c in columns if c.get("deterministic", False)
            ),
            "note": (
                "no column was eligible: every one was either below the minimum "
                "sample size or a deterministic calendar column"
            ),
        }

    alerting = [c for c in scored if c["severity"] == Severity.ALERT.value]
    warning = [c for c in scored if c["severity"] == Severity.WARN.value]
    share = len(alerting) / len(scored)

    if len(scored) == 1:
        severity = Severity(scored[0]["severity"])
    elif share >= thresholds.drifted_share_alert:
        severity = Severity.ALERT
    elif alerting or share >= thresholds.drifted_share_warn or warning:
        severity = Severity.WARN
    else:
        severity = Severity.OK

    worst = max(scored, key=lambda c: c["psi"]["psi"])
    return severity, {
        "columns_scored": len(scored),
        "columns_alerting": len(alerting),
        "columns_warning": len(warning),
        "columns_excluded_deterministic": sorted(
            c["column"] for c in columns if c.get("deterministic", False)
        ),
        "drifted_share": round(share, 4),
        "max_psi": worst["psi"]["psi"],
        "max_psi_column": worst["column"],
    }


# ---------------------------------------------------------------------------
# 1. feature drift
# ---------------------------------------------------------------------------
def feature_drift(
    windows: ScoredWindows,
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
    columns: tuple[str, ...] | None = None,
) -> DriftSection:
    """PSI + KS on every model input, ranked worst-first."""
    columns = columns or build_mod.FEATURE_COLUMNS
    per_column = [
        compare_column(
            windows.reference[name],
            windows.current[name],
            name,
            thresholds,
            with_bins=False,
        )
        for name in columns
        if name in windows.reference.columns
    ]
    # Worst first, but the deterministic calendar columns sink to the bottom:
    # they do not vote, so they should not head the table a human reads either.
    per_column.sort(key=lambda c: (not c["deterministic"], c["psi"]["psi"]), reverse=True)

    severity, rollup = _section_from_columns("feature", per_column, thresholds)
    if rollup.get("columns_scored", 0) == 0:
        summary = "not enough rows in one of the windows to score feature drift"
    else:
        summary = (
            f"{rollup['columns_alerting']}/{rollup['columns_scored']} feature(s) above "
            f"PSI {thresholds.psi_alert}; worst is {rollup['max_psi_column']} "
            f"at PSI {rollup['max_psi']:.3f}"
        )

    return DriftSection(
        drift_type="feature",
        severity=severity,
        summary=summary,
        details={
            "description": "distribution shift in the model inputs (leading indicator)",
            "note": (
                "deterministic calendar columns are reported but excluded from the "
                "verdict — their PSI measures which dates the windows cover, not the data"
            ),
            **rollup,
            "columns": per_column,
        },
    )


# ---------------------------------------------------------------------------
# 2. target drift
# ---------------------------------------------------------------------------
def target_drift(
    windows: ScoredWindows,
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
) -> DriftSection:
    """Has the demand distribution itself moved between the two windows?"""
    column = compare_column(
        windows.reference[build_mod.TARGET_COLUMN],
        windows.current[build_mod.TARGET_COLUMN],
        "y_actual_demand_mwh",
        thresholds,
        with_bins=True,
    )
    severity, rollup = _section_from_columns("target", [column], thresholds)
    shift = column["distribution"]["mean_shift"]

    return DriftSection(
        drift_type="target",
        severity=severity,
        summary=(
            f"actual demand PSI {column['psi']['psi']:.3f}, mean moved "
            f"{shift:+,.0f} MWh between the reference and current windows"
            if shift is not None
            else "not enough rows to score target drift"
        ),
        details={
            "description": "distribution shift in the observed demand (a new load regime)",
            **rollup,
            "columns": [column],
        },
    )


# ---------------------------------------------------------------------------
# 3. prediction drift
# ---------------------------------------------------------------------------
def prediction_drift(
    windows: ScoredWindows,
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
) -> DriftSection:
    """Has the model's output distribution moved? Computable without labels."""
    column = compare_column(
        windows.reference[PREDICTION_COLUMN],
        windows.current[PREDICTION_COLUMN],
        "yhat_forecast_mwh",
        thresholds,
        with_bins=True,
    )
    severity, rollup = _section_from_columns("prediction", [column], thresholds)
    shift = column["distribution"]["mean_shift"]

    return DriftSection(
        drift_type="prediction",
        severity=severity,
        summary=(
            f"forecast PSI {column['psi']['psi']:.3f}, mean moved {shift:+,.0f} MWh "
            "(label-free signal: available before the actuals arrive)"
            if shift is not None
            else "not enough rows to score prediction drift"
        ),
        details={
            "description": (
                "distribution shift in the model output; the only drift signal that "
                "needs no ground truth, so it is the earliest one available"
            ),
            **rollup,
            "columns": [column],
        },
    )


# ---------------------------------------------------------------------------
# 4. performance drift
# ---------------------------------------------------------------------------
def _window_errors(frame: pd.DataFrame) -> dict:
    absolute = frame[ABS_ERROR_COLUMN].dropna()
    percentage = frame[ABS_PCT_ERROR_COLUMN].dropna()
    if absolute.empty:
        return {"n": 0, "mae": None, "mape_pct": None, "rmse": None, "bias": None}
    return {
        "n": len(absolute),
        "mae": round(float(absolute.mean()), 4),
        "mape_pct": round(float(percentage.mean()), 4) if len(percentage) else None,
        "rmse": round(float(np.sqrt(np.mean(np.square(frame[ERROR_COLUMN].dropna())))), 4),
        "bias": round(float(frame[ERROR_COLUMN].dropna().mean()), 4),
    }


def rolling_error_series(
    windows: ScoredWindows,
    window_hours: int = DEFAULT_THRESHOLDS.rolling_window_hours,
) -> pd.DataFrame:
    """Daily MAE/MAPE across both windows, plus their rolling mean.

    Aggregated by the *target* day rather than by the forecast origin: a
    monitoring chart answers "how wrong were we about Tuesday", and that is a
    property of Tuesday, not of the moment the forecast was made.
    """
    frame = pd.concat(
        [windows.reference.assign(window="reference"), windows.current.assign(window="current")],
        ignore_index=True,
    )
    frame = frame.assign(day=pd.DatetimeIndex(frame["target_utc"]).floor("D"))

    daily = (
        frame.groupby("day")
        .agg(
            mae=(ABS_ERROR_COLUMN, "mean"),
            mape_pct=(ABS_PCT_ERROR_COLUMN, "mean"),
            bias=(ERROR_COLUMN, "mean"),
            n=(ABS_ERROR_COLUMN, "size"),
            window=("window", "last"),
        )
        .reset_index()
        .sort_values("day")
    )

    span_days = max(1, window_hours // 24)
    daily["mae_rolling"] = daily["mae"].rolling(span_days, min_periods=1).mean()
    daily["mape_rolling"] = daily["mape_pct"].rolling(span_days, min_periods=1).mean()
    return daily


def performance_drift(
    windows: ScoredWindows,
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
) -> DriftSection:
    """Rolling MAE / MAPE degradation of the frozen model, current vs reference.

    Both windows are out of sample for the booster (see `drift.windows`), so a
    difference between them is a property of the world, not of the fit.
    """
    reference = _window_errors(windows.reference)
    current = _window_errors(windows.current)
    daily = rolling_error_series(windows, thresholds.rolling_window_hours)

    if not reference["n"] or not current["n"] or not reference["mae"]:
        return DriftSection(
            drift_type="performance",
            severity=Severity.OK,
            summary="not enough scored rows to measure performance drift",
            details={
                "description": "degradation of the rolling forecast error",
                "status": INSUFFICIENT_DATA,
                "reference": reference,
                "current": current,
                "rolling": [],
            },
        )

    mae_ratio = current["mae"] / reference["mae"] - 1.0
    mape_delta_pp = (
        current["mape_pct"] - reference["mape_pct"]
        if current["mape_pct"] is not None and reference["mape_pct"] is not None
        else None
    )

    severities = [Severity.OK]
    if mae_ratio >= thresholds.mae_degradation_alert:
        severities.append(Severity.ALERT)
    elif mae_ratio >= thresholds.mae_degradation_warn:
        severities.append(Severity.WARN)

    if mape_delta_pp is not None:
        if mape_delta_pp >= thresholds.mape_degradation_alert_pp:
            severities.append(Severity.ALERT)
        elif mape_delta_pp >= thresholds.mape_degradation_warn_pp:
            severities.append(Severity.WARN)

    severity = Severity.worst(severities)
    peak = daily.loc[daily["mae_rolling"].idxmax()] if len(daily) else None

    return DriftSection(
        drift_type="performance",
        severity=severity,
        summary=(
            f"MAE {reference['mae']:,.0f} -> {current['mae']:,.0f} MWh "
            f"({mae_ratio:+.1%})"
            + (f", MAPE {mape_delta_pp:+.2f} pp" if mape_delta_pp is not None else "")
        ),
        details={
            "description": (
                "degradation of the frozen model's rolling error; the only signal that "
                "proves harm, and the slowest, because it waits for the actuals"
            ),
            "reference": reference,
            "current": current,
            "mae_degradation": round(float(mae_ratio), 6),
            "mape_degradation_pp": round(float(mape_delta_pp), 4)
            if mape_delta_pp is not None
            else None,
            "rolling_window_hours": thresholds.rolling_window_hours,
            "worst_rolling_mae": round(float(peak["mae_rolling"]), 4) if peak is not None else None,
            "worst_rolling_mae_day_utc": peak["day"].isoformat() if peak is not None else None,
            "rolling": [
                {
                    "day_utc": row.day.isoformat(),
                    "window": row.window,
                    "mae": round(float(row.mae), 2),
                    "mape_pct": round(float(row.mape_pct), 4),
                    "bias": round(float(row.bias), 2),
                    "mae_rolling": round(float(row.mae_rolling), 2),
                    "mape_rolling": round(float(row.mape_rolling), 4),
                    "n": int(row.n),
                }
                for row in daily.itertuples(index=False)
            ],
        },
    )


# ---------------------------------------------------------------------------
# drift over time
# ---------------------------------------------------------------------------
def drift_timeline(
    windows: ScoredWindows,
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
    window_days: int = 7,
) -> list[dict]:
    """PSI of a trailing window against the reference, one point per day.

    The four sections above answer "is there drift *now*". This answers "since
    when", which is the question anyone actually asks when an alarm goes off —
    and it is the series the dashboard plots.

    Each point compares the trailing `window_days` ending that day against the
    **whole reference window**. Points that fall inside the reference are
    therefore partly self-comparisons, and that is deliberate: they show what
    normal PSI wobble looks like for this data, which is the only way to read
    whether a later excursion is large. The alternative — starting the series at
    the current window — gives a chart with no baseline on it.
    """
    frame = pd.concat(
        [windows.reference.assign(window="reference"), windows.current.assign(window="current")],
        ignore_index=True,
    )
    if frame.empty:
        return []

    targets = pd.DatetimeIndex(frame["target_utc"])
    frame = frame.assign(day=targets.floor("D"))

    reference = windows.reference
    scored_features = [
        name
        for name in build_mod.FEATURE_COLUMNS
        if name not in DETERMINISTIC_COLUMNS and name in reference.columns
    ]

    span = pd.Timedelta(days=window_days)
    points: list[dict] = []

    for day, rows in frame.groupby("day", sort=True):
        trailing = frame[(frame["day"] <= day) & (frame["day"] > day - span)]
        if len(trailing) < thresholds.min_samples:
            continue

        def psi(column: str, trailing: pd.DataFrame = trailing) -> float:
            return stats.population_stability_index(
                reference[column],
                trailing[column],
                bins=thresholds.psi_bins,
                max_categorical_levels=thresholds.max_categorical_levels,
            ).psi

        feature_psis = {name: psi(name) for name in scored_features}
        worst = max(feature_psis, key=feature_psis.get) if feature_psis else None

        points.append(
            {
                "day_utc": pd.Timestamp(day).isoformat(),
                "window": rows["window"].iloc[-1],
                "n": len(trailing),
                "target_psi": round(psi(build_mod.TARGET_COLUMN), 6),
                "prediction_psi": round(psi(PREDICTION_COLUMN), 6),
                "feature_max_psi": round(float(feature_psis[worst]), 6) if worst else None,
                "feature_max_column": worst,
                "mae": round(float(rows[ABS_ERROR_COLUMN].mean()), 2),
            }
        )

    return points


def run_all(
    windows: ScoredWindows,
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
) -> dict[str, DriftSection]:
    """All four detectors, keyed by drift type — the body of `metrics/drift.json`."""
    return {
        "feature": feature_drift(windows, thresholds),
        "target": target_drift(windows, thresholds),
        "prediction": prediction_drift(windows, thresholds),
        "performance": performance_drift(windows, thresholds),
    }
