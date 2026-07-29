"""An Evidently report alongside the hand-rolled detectors — deliberately both.

Why run two implementations of the same idea
--------------------------------------------
The hand-rolled PSI/KS in `drift.stats` is what the pipeline acts on: it is
auditable line by line, it has no runtime dependency, and its thresholds are
this project's own. Evidently is run next to it as an **independent second
opinion** — a widely-used library disagreeing with our number would be a bug in
our number, and the artifact records both so the disagreement is visible rather
than assumed away.

Evidently's `ValueDrift` picks its own test per column (K-S for numerical
columns at these sample sizes, chi-square / Jensen-Shannon for categorical
ones) and its own thresholds. It is *not* wired into the retrain trigger; it is
evidence, and it also renders the HTML report a human actually looks at.

Evidently is an **optional dev dependency**. It pulls a large tree (litestar,
plotly, nltk...) and the daily pipeline must not fail because it is missing, so
every entry point here degrades to a recorded `"status": "unavailable"` instead
of raising.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from drift.windows import PREDICTION_COLUMN, ScoredWindows
from features import build as build_mod

log = logging.getLogger(__name__)

# Reported as-is in the artifact so a run explains why the section is empty.
UNAVAILABLE = "unavailable"
OK = "ok"
FAILED = "failed"


def is_available() -> bool:
    """True when Evidently can be imported in this environment."""
    try:
        import evidently  # noqa: F401
    except ImportError:
        return False
    return True


def _frames(windows: ScoredWindows) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    """The two frames Evidently compares: features + target + prediction."""
    numerical = [
        column
        for column in build_mod.FEATURE_COLUMNS
        if column not in build_mod.CATEGORICAL_FEATURES
    ]
    numerical += [build_mod.TARGET_COLUMN, PREDICTION_COLUMN]
    categorical = list(build_mod.CATEGORICAL_FEATURES)
    columns = numerical + categorical

    reference = windows.reference[columns].copy()
    current = windows.current[columns].copy()
    return reference, current, numerical, categorical


def build_report(
    windows: ScoredWindows,
    html_path: Path | None = None,
) -> dict:
    """Run Evidently's data-drift preset; return a JSON-safe summary.

    Never raises: a missing or broken Evidently is recorded in the returned
    dict, because the daily cron must keep producing `metrics/drift.json`.
    """
    if not is_available():
        return {
            "status": UNAVAILABLE,
            "reason": (
                "evidently is not installed; it is an optional dev dependency "
                "(`uv sync --extra dev`). The hand-rolled PSI/KS detectors are "
                "unaffected — they are what the retrain trigger reads."
            ),
        }

    try:
        from evidently import DataDefinition, Dataset, Report
        from evidently.presets import DataDriftPreset

        reference, current, numerical, categorical = _frames(windows)
        definition = DataDefinition(
            numerical_columns=numerical,
            categorical_columns=categorical,
        )
        report = Report([DataDriftPreset()])
        snapshot = report.run(
            Dataset.from_pandas(current, data_definition=definition),
            Dataset.from_pandas(reference, data_definition=definition),
        )
        summary = _summarise(snapshot.dict())

        if html_path is not None:
            html_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot.save_html(str(html_path))
            summary["html_report"] = f"{html_path.parent.name}/{html_path.name}"
            summary["html_report_note"] = (
                "local artifact only — ~5MB of inlined plotly, written outside metrics/ "
                "and gitignored"
            )

        import evidently

        summary["evidently_version"] = evidently.__version__
        return summary

    except Exception as exc:
        log.warning(
            "Evidently report failed (%s: %s) — continuing without it.", type(exc).__name__, exc
        )
        return {"status": FAILED, "error": f"{type(exc).__name__}: {exc}"}


def _summarise(payload: dict) -> dict:
    """Flatten Evidently's metric list into per-column drift scores."""
    columns: list[dict] = []
    drifted_count = drifted_share = None

    for metric in payload.get("metrics", []):
        name = metric.get("metric_name", "")
        config = metric.get("config", {})
        value = metric.get("value")

        if config.get("type", "").endswith("DriftedColumnsCount") and isinstance(value, dict):
            drifted_count = value.get("count")
            drifted_share = value.get("share")
        elif config.get("type", "").endswith("ValueDrift"):
            columns.append(
                {
                    "column": config.get("column"),
                    "method": config.get("method"),
                    "score": round(float(value), 8) if isinstance(value, int | float) else value,
                    "threshold": config.get("threshold"),
                    "drift_detected": (
                        bool(value < config["threshold"])
                        if isinstance(value, int | float) and "threshold" in config
                        else None
                    ),
                    "metric_name": name,
                }
            )

    return {
        "status": OK,
        "note": (
            "independent second opinion; Evidently picks its own test and thresholds "
            "per column and is NOT wired into the retrain trigger"
        ),
        "drifted_columns": drifted_count,
        "drifted_share": drifted_share,
        "columns": columns,
    }
