"""`uv run python -m pipeline.daily` — the whole loop, once, in order (M5).

    ingest -> features -> score -> rolling-MAE monitor -> drift -> metrics/ + PNGs

This is the single entrypoint `.github/workflows/daily.yml` calls. Everything
the cron needs to do lives here rather than in YAML, for the obvious reason:
a shell pipeline spread across ten workflow steps can only be tested by pushing
to GitHub, whereas this one runs locally and has tests.

Structure
---------
Each stage is a `@step` that records its status, how long it took, and a short
detail block. The run record is written to `metrics/pipeline.json` whether the
run succeeded or not, so a failed cron leaves an artifact explaining itself
instead of only a red tick in the Actions tab.

Ingestion is the one stage allowed to degrade: a source being down (or the EIA
key not existing yet) must not stop the model from being re-scored on the
history already in the lake. Everything after it is fatal, because a scoring
step that silently half-worked is worse than a failed run.

Honesty
-------
Every artifact this writes carries `"is_real"`, and it is false unless *both*
the panel and the serving model came from real data. The PNGs are watermarked
when it is false. `--require-eia-key` makes a missing key a hard failure with a
pointer to docs/BLOCKED.md — that is the mode the workflow uses, so a cron that
would silently publish fixture numbers dies instead.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    # Import-time cost matters here: `lightgbm` is the slowest import in the
    # project and this module is the CLI entrypoint. `from __future__ import
    # annotations` makes every annotation a string, so these are needed only by
    # the type checker and never at runtime.
    import lightgbm as lgb

    from drift.detectors import DriftSection
    from drift.trigger import RetrainVerdict
    from drift.windows import ScoredWindows

from drift import detectors, evidently_report, trigger
from drift.config import DEFAULT_CURRENT_DAYS, DEFAULT_REFERENCE_DAYS, DriftThresholds
from drift.run import render_summary
from drift.windows import (
    PREDICTION_COLUMN,
    NoPostTrainingData,
    NotEnoughHistoryError,
    build_windows,
)
from features import build as build_mod
from features import panel as panel_mod
from ingest.config import INGEST_LEGS, METRICS_DIR, eia_api_key
from models import tracking
from models.data import SYNTHETIC_WARNING, NoRealDataError, resolve_panel
from pipeline import plots

log = logging.getLogger("pipeline.daily")

# The published surface. Every one of these is small, committed, and refreshed
# by this script; `metrics/` holds nothing else.
FORECAST_JSON = "forecast.json"
MONITOR_JSON = "monitor.json"
DRIFT_JSON = "drift.json"
DRIFT_SUMMARY = "drift_summary.md"
RUN_JSON = "pipeline.json"
FORECAST_PNG = "forecast_vs_actual.png"
ROLLING_PNG = "rolling_mae.png"

# The horizon the forecast-vs-actual chart shows. 24 h is the decision-relevant
# one for a day-ahead market and the hardest of the 24, so it is the honest one
# to publish; every horizon is still in metrics/model.json.
CHART_HORIZON_H = 24

MISSING_KEY_MESSAGE = (
    "EIA_API_KEY is not set.\n"
    "\n"
    "  This pipeline was started with --require-eia-key, which means it refuses to\n"
    "  publish metrics derived from the synthetic fixture. Register a free key at\n"
    "  https://www.eia.gov/opendata/register.php and either put EIA_API_KEY=... in\n"
    "  .env locally, or add it as a repository secret named EIA_API_KEY.\n"
    "\n"
    "  Full instructions: docs/BLOCKED.md\n"
    "  To run against the fixture instead, drop --require-eia-key."
)


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "degraded" | "failed" | "skipped"
    seconds: float
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "step": self.name,
            "status": self.status,
            "seconds": round(self.seconds, 2),
            **self.detail,
        }


class PipelineError(RuntimeError):
    """A fatal stage failed; the run record is still written."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="pipeline.daily", description=__doc__)
    p.add_argument("--source", choices=["auto", "real", "synthetic"], default="auto")
    p.add_argument("--fixture-days", type=int, default=200)
    p.add_argument(
        "--require-eia-key",
        action="store_true",
        help="fail immediately, with instructions, when EIA_API_KEY is unset "
        "(what the daily workflow uses, so a cron never publishes fixture numbers)",
    )
    p.add_argument("--skip-ingest", action="store_true", help="score what is already in the lake")
    p.add_argument(
        "--ingest-source",
        choices=list(INGEST_LEGS),
        default="all",
        help="which leg to pull",
    )
    p.add_argument("--full-refresh", action="store_true", help="re-pull the whole backfill window")
    p.add_argument(
        "--forecast-history-days",
        type=int,
        default=21,
        help="how much hourly forecast-vs-actual detail to publish (default: 21 days); "
        "the daily aggregates in monitor.json always cover both windows",
    )
    p.add_argument("--reference-days", type=int, default=DEFAULT_REFERENCE_DAYS)
    p.add_argument("--current-days", type=int, default=DEFAULT_CURRENT_DAYS)
    p.add_argument("--max-horizon", type=int, default=24)
    p.add_argument("--train-stride-hours", type=int, default=6)
    p.add_argument("--num-boost-round", type=int, default=300)
    p.add_argument(
        "--no-champion",
        action="store_true",
        help="always fit a fresh booster instead of loading the registry champion",
    )
    p.add_argument("--no-evidently", action="store_true", help="skip the optional second opinion")
    p.add_argument("--no-plots", action="store_true", help="skip the PNGs")
    p.add_argument("--out-dir", type=Path, default=METRICS_DIR)
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


class DailyPipeline:
    """One run of the loop. Instantiate, call `run()`, read `self.steps`."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.out_dir: Path = args.out_dir
        self.thresholds = DriftThresholds.from_env()
        self.steps: list[StepResult] = []
        self.started_at = datetime.now(UTC)

        self.panel: pd.DataFrame | None = None
        self.provenance: dict = {}
        # The champion is what `/forecast` serves and what the forward forecast
        # uses. The monitor model is what scored the two monitoring windows —
        # usually the same object, but *not* when the champion's training span
        # covers those windows (see `_monitoring_booster`).
        self.model_info: dict = {}
        self.monitor_model_info: dict = {}
        # Annotated rather than left to inference: these start as None and are
        # filled in by later stages, so without the annotation a type checker
        # infers `None` and every downstream attribute access looks like a bug.
        self.champion: lgb.Booster | None = None
        self.windows: ScoredWindows | None = None
        # Set only when the champion is younger than the first hour it could be
        # judged on; carried into the artifact so the state explains itself.
        self.no_drift_reason: str = ""
        self.sections: dict[str, DriftSection] = {}
        self.verdict: RetrainVerdict | None = None
        self.artifacts: list[str] = []

    # -- provenance ---------------------------------------------------------
    @property
    def is_real(self) -> bool:
        """Real only when the data *and* the model are. Either alone is not enough.

        A champion trained on the fixture keeps the run synthetic even after real
        demand lands in the lake — until it is retrained, the served forecast is
        still a fixture artifact. When there is no champion, every booster in the
        run was fitted here on the current panel, so the panel decides alone.
        """
        if not self.provenance.get("is_real"):
            return False
        if self.champion is None:
            return True
        return bool(self.model_info.get("trained_on_real_data", False))

    @property
    def warning(self) -> str | None:
        return None if self.is_real else SYNTHETIC_WARNING

    def _stamp(self, payload: dict) -> dict:
        """The provenance header every published artifact starts with."""
        return {
            "milestone": "M5",
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "is_real": self.is_real,
            "warning": self.warning,
            **payload,
        }

    def _write(self, name: str, payload: dict) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.artifacts.append(name)
        log.info("wrote %s", path)
        return path

    # -- stages -------------------------------------------------------------
    def _timed(self, name: str, fn) -> StepResult:
        start = time.perf_counter()
        try:
            status, detail = fn()
        except PipelineError:
            raise
        except Exception as exc:
            elapsed = time.perf_counter() - start
            self.steps.append(
                StepResult(name, "failed", elapsed, {"error": f"{type(exc).__name__}: {exc}"})
            )
            raise PipelineError(f"step `{name}` failed: {exc}") from exc

        result = StepResult(name, status, time.perf_counter() - start, detail)
        self.steps.append(result)
        log.info("[%s] %s in %.1fs", name, status, result.seconds)
        return result

    def step_ingest(self) -> tuple[str, dict]:
        """Pull the delta from both sources. Allowed to degrade, never to stop the run."""
        if self.args.skip_ingest:
            return "skipped", {"reason": "--skip-ingest"}

        from ingest.__main__ import main as ingest_main

        argv = ["--source", self.args.ingest_source]
        if self.args.full_refresh:
            argv.append("--full-refresh")

        try:
            code = ingest_main(argv)
        except Exception as exc:
            log.warning("Ingestion raised (%s) — scoring what is already in the lake.", exc)
            return "degraded", {"error": f"{type(exc).__name__}: {exc}"}

        if code != 0:
            return "degraded", {
                "exit_code": code,
                "note": "at least one source failed; scoring the history already in the lake",
            }
        return "ok", {"sources": self.args.ingest_source}

    def step_features(self) -> tuple[str, dict]:
        """Resolve the modelling panel — the lake if it has demand, else the fixture."""
        try:
            self.panel, self.provenance = resolve_panel(
                self.args.source, fixture_days=self.args.fixture_days
            )
        except NoRealDataError as exc:
            raise PipelineError(str(exc)) from exc

        described = panel_mod.describe_panel(self.panel)
        return ("ok" if self.provenance["is_real"] else "degraded"), {
            "kind": self.provenance["kind"],
            "is_real": self.provenance["is_real"],
            "panel": described,
        }

    def _load_champion(self) -> None:
        """Resolve the model that serving would return, or record why there isn't one."""
        if self.args.no_champion:
            self.model_info = {"source": "none", "reason": "--no-champion"}
            return
        try:
            self.champion, self.model_info = tracking.load_champion()
        except tracking.ChampionUnavailable as exc:
            log.warning("No registry champion (%s).", exc)
            self.model_info = {"source": "none", "reason": str(exc)}

    def _monitoring_booster(self, reference_start: pd.Timestamp):
        """The champion — but only if it never saw the windows it would be judged on.

        This is the trap that makes a drift monitor lie. The registry champion is
        refit on *all* available history, so by the time it is promoted it has
        already learned the reference and current windows. Scoring them with it
        yields in-sample errors — on this fixture, an MAE of ~1,000 MWh against
        the ~2,300 the same model gets out of sample. Every future window then
        looks catastrophically degraded against a reference that was never real.

        So the champion is used to score the monitoring windows **only** when its
        `train_data_end_utc` tag proves its training data stopped before the
        reference window opens. Otherwise the monitor fits its own booster on the
        train slice and says so, in the artifact, with the reason. A missing tag
        counts as ineligible: unknown is not safe.
        """
        if self.champion is None:
            return None, {
                "source": "fitted_on_train_window",
                "reason": self.model_info.get("reason", "no registry champion available"),
            }

        trained_to = self.model_info.get("train_data_end_utc")
        if trained_to is None:
            return None, {
                "source": "fitted_on_train_window",
                "reason": (
                    "the champion does not record `train_data_end_utc`, so it cannot be "
                    "shown to be out of sample on the monitoring windows"
                ),
                "champion_version": self.model_info.get("version"),
            }

        if pd.Timestamp(trained_to) >= reference_start:
            return None, {
                "source": "fitted_on_train_window",
                "reason": (
                    f"the champion was trained on data up to {trained_to}, which covers the "
                    f"reference window opening at {reference_start.isoformat()}; scoring it "
                    "there would be in-sample"
                ),
                "champion_version": self.model_info.get("version"),
                "champion_train_data_end_utc": trained_to,
            }

        return self.champion, {
            "source": "mlflow_registry",
            "reason": f"the champion's training data ends at {trained_to}, before the window",
            "champion_version": self.model_info.get("version"),
            "champion_train_data_end_utc": trained_to,
        }

    def step_score(self) -> tuple[str, dict]:
        """Load the champion, then score the two monitoring windows out of sample."""
        self._load_champion()

        end = self.panel.index.max()

        # The boundary that makes drift a question about the model rather than
        # about the calendar: everything after it is data the champion never
        # learned. Only a champion that reports when its training data ends can
        # provide it; without one the windows fall back to sliding with `end`,
        # which is the old behaviour and is all that is available.
        trained_to = self.model_info.get("train_data_end_utc")
        anchor = pd.Timestamp(trained_to) if trained_to else None

        if anchor is not None:
            reference_start = anchor - pd.Timedelta(days=self.args.reference_days)
        else:
            reference_start = end - pd.Timedelta(
                days=self.args.current_days + self.args.reference_days
            )
        booster, self.monitor_model_info = self._monitoring_booster(reference_start)

        try:
            self.windows = build_windows(
                self.panel,
                reference_days=self.args.reference_days,
                current_days=self.args.current_days,
                horizons=tuple(range(1, self.args.max_horizon + 1)),
                stride_hours=self.args.train_stride_hours,
                num_boost_round=self.args.num_boost_round,
                booster=booster,
                anchor=anchor,
            )
        except NoPostTrainingData as exc:
            # Green and empty, not red. The champion is younger than the first
            # hour it would be judged on, so there is nothing to judge. Failing
            # here would paint a freshly retrained model as broken.
            self.windows = None
            self.no_drift_reason = str(exc)
            log.info("No post-training data yet: %s", exc)
            return "ok", {
                "served_model": self.model_info,
                "monitoring_model": {
                    "source": "none",
                    "reason": "the champion has no data after it to be scored on",
                },
                "drift_measurable": False,
                "anchor_utc": anchor.isoformat() if anchor is not None else None,
            }
        except NotEnoughHistoryError as exc:
            raise PipelineError(str(exc)) from exc

        # Structure said the window exists; policy decides whether it can speak.
        # Anchored at the end of training, "a few hours have arrived" leaves a
        # handful of rows rather than none, and a verdict computed from a
        # handful is noise wearing a rule name. `min_samples` is the floor the
        # detectors already use for exactly this, applied here to the window as
        # a whole.
        if anchor is not None and len(self.windows.current) < self.thresholds.min_samples:
            reason = (
                f"only {len(self.windows.current)} scored row(s) have arrived since the "
                f"champion stopped learning at {anchor.isoformat()}; "
                f"{self.thresholds.min_samples} are needed to measure drift."
            )
            self.windows = None
            self.no_drift_reason = reason
            log.info("Not enough post-training data yet: %s", reason)
            return "ok", {
                "served_model": self.model_info,
                "monitoring_model": {
                    "source": "none",
                    "reason": "too little data after the champion to score it",
                },
                "drift_measurable": False,
                "anchor_utc": anchor.isoformat(),
            }

        return "ok", {
            "served_model": self.model_info,
            "monitoring_model": self.monitor_model_info,
            "rows": self.windows.split["rows"],
        }

    def step_forecast(self) -> tuple[str, dict]:
        """`metrics/forecast.json` + the forecast-vs-actual PNG."""
        history = self._chart_history()
        forward = self._forward_forecast()

        payload = self._stamp(
            {
                "units": "MWh",
                "served_model": self.model_info,
                "monitoring_model": self.monitor_model_info,
                "data": {k: v for k, v in self.provenance.items() if k != "warning"},
                "horizon_shown_h": CHART_HORIZON_H,
                "note": (
                    f"`history` is the day-ahead forecast (largest horizon within "
                    f"{CHART_HORIZON_H}h, one row per target hour) scored against the actual "
                    "that later arrived; `forward` is the live forecast from the latest "
                    "origin, whose actuals do not exist yet"
                ),
                "history": [
                    {
                        "target_utc": pd.Timestamp(row.target_utc).isoformat(),
                        "horizon_h": int(row.horizon_h),
                        "actual_mwh": round(float(row.actual_mwh), 1),
                        "forecast_mwh": round(float(row.forecast_mwh), 1),
                        "error_mwh": round(float(row.forecast_mwh - row.actual_mwh), 1),
                    }
                    for row in history.itertuples(index=False)
                ],
                "forward": forward,
            }
        )
        self._write(FORECAST_JSON, payload)

        if not self.args.no_plots and not history.empty:
            path = plots.forecast_vs_actual(
                history,
                self.out_dir / FORECAST_PNG,
                is_real=self.is_real,
                title=(
                    f"Day-ahead forecast vs actual (horizon ≤ {CHART_HORIZON_H}h) — "
                    f"{self.provenance['kind']}"
                ),
            )
            self.artifacts.append(path.name)

        return "ok", {"history_points": len(history), "forward_points": len(forward)}

    def step_monitor(self) -> tuple[str, dict]:
        """The rolling-MAE monitor: `metrics/monitor.json` + its PNG.

        Computed from the same `performance` section the drift verdict reads, so
        the chart and the alarm can never tell different stories.
        """
        if self.windows is None:
            # The champion is younger than the first hour it could be judged on.
            # Publishing zeros here would read as "no error", which is a claim;
            # the truth is that nothing has been measured yet, and the artifact
            # says exactly that.
            self.sections = {}
            self._write(
                MONITOR_JSON,
                self._stamp(
                    {
                        "units": {"mae": "MWh", "mape_pct": "%", "bias": "MWh"},
                        "monitoring_model": self.monitor_model_info,
                        "served_model": self.model_info,
                        "measurable": False,
                        "reason": self.no_drift_reason,
                        "severity": "ok",
                        "summary": "no data has arrived since the champion stopped learning",
                        "daily": [],
                    }
                ),
            )
            return "ok", {"measurable": False}

        self.sections = detectors.run_all(self.windows, self.thresholds)
        performance = self.sections["performance"].details

        reference_mae = performance["reference"]["mae"]
        alert_line = (
            None
            if reference_mae is None
            else round(reference_mae * (1.0 + self.thresholds.mae_degradation_alert), 2)
        )

        payload = self._stamp(
            {
                "units": {"mae": "MWh", "mape_pct": "%", "bias": "MWh"},
                "monitoring_model": self.monitor_model_info,
                "served_model": self.model_info,
                "rolling_window_hours": self.thresholds.rolling_window_hours,
                "windows": self.windows.split,
                "reference": performance["reference"],
                "current": performance["current"],
                "mae_degradation": performance["mae_degradation"],
                "mape_degradation_pp": performance["mape_degradation_pp"],
                "alert_line_mae": alert_line,
                "severity": self.sections["performance"].severity.value,
                "summary": self.sections["performance"].summary,
                "daily": performance["rolling"],
            }
        )
        self._write(MONITOR_JSON, payload)

        if not self.args.no_plots and performance["rolling"]:
            daily = pd.DataFrame(performance["rolling"])
            daily["day_utc"] = pd.to_datetime(daily["day_utc"])
            path = plots.rolling_mae(
                daily,
                self.out_dir / ROLLING_PNG,
                is_real=self.is_real,
                reference_mae=reference_mae,
                alert_ratio=self.thresholds.mae_degradation_alert,
            )
            self.artifacts.append(path.name)

        return "ok", {
            "severity": self.sections["performance"].severity.value,
            "days": len(performance["rolling"]),
        }

    def _drift_not_measurable_yet(self) -> tuple[str, dict]:
        """The state every retrain passes through, published as itself.

        The alternative was to keep sliding the windows with the wall clock, and
        that is what produced a verdict on 2026-08-02 asserting "a regime the
        model was never fitted on" about two windows entirely inside the
        champion's own training set. Drift is measured against the end of
        training, so a champion trained to the end of the panel has nothing yet
        to be measured on. Saying so is the honest artifact; inventing a verdict
        is not, and `retrain` in particular is a claim about a model that has
        just been refit.
        """
        payload = {
            "milestone": "M4",
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "is_real": self.is_real,
            "warning": self.warning,
            "measurable": False,
            "reason": self.no_drift_reason,
            "verdict": {
                "should_retrain": False,
                "action": "none",
                "severity": "ok",
                "rule": "R0_champion_is_current",
                "rationale": (
                    "The champion was trained through the end of the available data, so no "
                    "hour has arrived yet that it did not learn from. Drift is measured "
                    "against the end of training; there is nothing after it to measure. "
                    "This is what every run looks like straight after a retrain, and the "
                    "signals below start accumulating as fresh data arrives."
                ),
                "signals": {},
                "reasons": [],
            },
            "thresholds": self.thresholds.as_dict(),
            "data": {**self.provenance, "panel": panel_mod.describe_panel(self.panel)},
            "monitoring_model": self.monitor_model_info,
            "served_model": self.model_info,
            "drift": {},
            "timeline": {
                "description": "no post-training data yet",
                "trailing_window_days": 7,
                "points": [],
            },
            "evidently": {"status": "skipped", "reason": "no post-training data"},
        }
        self._write(DRIFT_JSON, payload)

        summary_path = self.out_dir / DRIFT_SUMMARY
        summary_path.write_text(
            "# Drift\n\nNothing to measure yet: the champion was trained through the end of "
            "the available data.\n",
            encoding="utf-8",
        )
        self.artifacts.append(DRIFT_SUMMARY)
        return "ok", {"action": "none", "rule": "R0_champion_is_current", "measurable": False}

    def step_drift(self) -> tuple[str, dict]:
        """All four detectors + the retrain verdict -> `metrics/drift.json`."""
        if self.windows is None:
            return self._drift_not_measurable_yet()

        self.verdict = trigger.evaluate(self.sections, self.thresholds)

        if self.args.no_evidently:
            evidently = {"status": "skipped", "reason": "--no-evidently"}
        else:
            evidently = evidently_report.build_report(self.windows, html_path=None)

        payload = {
            "milestone": "M4",
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "is_real": self.is_real,
            "warning": self.warning,
            "verdict": self.verdict.as_dict(),
            "thresholds": self.thresholds.as_dict(),
            "windows": self.windows.split,
            "data": {**self.provenance, "panel": panel_mod.describe_panel(self.panel)},
            "monitoring_model": self.monitor_model_info,
            "served_model": self.model_info,
            "drift": {name: section.as_dict() for name, section in self.sections.items()},
            "timeline": {
                "description": (
                    "PSI of a trailing 7-day window against the whole reference window, "
                    "one point per day — the drift-over-time series the dashboard plots"
                ),
                "trailing_window_days": 7,
                "points": detectors.drift_timeline(self.windows, self.thresholds),
            },
            "evidently": evidently,
        }
        self._write(DRIFT_JSON, payload)

        summary_path = self.out_dir / DRIFT_SUMMARY
        summary_path.write_text(render_summary(payload), encoding="utf-8")
        self.artifacts.append(DRIFT_SUMMARY)

        return "ok", {
            "action": self.verdict.action,
            "should_retrain": self.verdict.should_retrain,
            "signals": self.verdict.signals,
        }

    # -- helpers ------------------------------------------------------------
    def _chart_history(self) -> pd.DataFrame:
        """One day-ahead forecast per target hour, against the actual that arrived.

        A target hour appears on several design rows — one per origin that could
        still reach it. Filtering to `horizon_h == 24` exactly would leave only
        the hours some origin happens to land 24 h before, which at a 6 h origin
        stride is a quarter of them, and the chart would be a dotted line rather
        than a curve. So for each target hour this takes the row with the
        **largest horizon within the day-ahead window** — the earliest forecast
        that was still a day-ahead forecast, which is also the hardest one.
        """
        if self.windows is None:
            # Not a stage-ordering bug any more: since the windows are anchored
            # on the end of training, a champion trained right up to the end of
            # the panel legitimately produces none. There is then no scored
            # history to chart — the forward forecast below is still published,
            # and the empty frame is the honest input for it.
            return pd.DataFrame(columns=["target_utc", "actual_mwh", "forecast_mwh"])

        frame = pd.concat([self.windows.reference, self.windows.current], ignore_index=True)
        horizon = min(CHART_HORIZON_H, self.args.max_horizon)
        frame = frame[(frame["horizon_h"] <= horizon) & frame[build_mod.TARGET_COLUMN].notna()]
        if frame.empty:
            return frame.rename(
                columns={build_mod.TARGET_COLUMN: "actual_mwh", PREDICTION_COLUMN: "forecast_mwh"}
            )[["target_utc", "actual_mwh", "forecast_mwh"]]

        chosen = frame.loc[frame.groupby("target_utc")["horizon_h"].idxmax()]
        chosen = chosen.sort_values("target_utc")

        # Hourly detail is only published for the recent tail; the daily
        # aggregates in monitor.json cover the whole span, so nothing is lost
        # except a few hundred KB of committed JSON nobody would read.
        cutoff = chosen["target_utc"].max() - pd.Timedelta(days=self.args.forecast_history_days)
        chosen = chosen[chosen["target_utc"] >= cutoff]

        return chosen.rename(
            columns={build_mod.TARGET_COLUMN: "actual_mwh", PREDICTION_COLUMN: "forecast_mwh"}
        )[["target_utc", "horizon_h", "actual_mwh", "forecast_mwh"]]

    def _forward_forecast(self) -> list[dict]:
        """The live forecast: from the first hour after the last observed demand.

        Served by the **champion** whenever there is one — this is the same
        answer `/forecast` gives, and it would be odd for the dashboard and the
        API to disagree. Its actuals do not exist yet, which is the point: it is
        kept separate from the scored history so the two can never be plotted as
        the same thing.
        """
        observed = self.panel[panel_mod.DEMAND_COLUMN].dropna()
        if observed.empty:
            return []

        origin = observed.index.max() + pd.Timedelta(hours=1)
        horizons = tuple(range(1, self.args.max_horizon + 1))
        design = build_mod.build_design_matrix(self.panel, pd.DatetimeIndex([origin]), horizons)
        if design.empty:
            return []

        booster = self.champion if self.champion is not None else self.windows.booster
        predictions = booster.predict(build_mod.feature_frame(design))
        return [
            {
                "horizon_h": int(row.horizon_h),
                "target_utc": pd.Timestamp(row.target_utc).isoformat(),
                "forecast_mwh": round(float(prediction), 1),
            }
            for row, prediction in zip(design.itertuples(index=False), predictions, strict=True)
        ]

    # -- the run ------------------------------------------------------------
    def run(self) -> dict:
        stages = (
            ("ingest", self.step_ingest),
            ("features", self.step_features),
            ("score", self.step_score),
            ("forecast", self.step_forecast),
            ("monitor", self.step_monitor),
            ("drift", self.step_drift),
        )

        status = "ok"
        error = None
        try:
            for name, fn in stages:
                self._timed(name, fn)
        except PipelineError as exc:
            status, error = "failed", str(exc)
            log.error("Pipeline failed: %s", exc)

        record = self._stamp(
            {
                "milestone": "M5",
                "status": status,
                "error": error,
                "started_at_utc": self.started_at.isoformat(timespec="seconds"),
                "seconds": round((datetime.now(UTC) - self.started_at).total_seconds(), 2),
                "entrypoint": "python -m pipeline.daily",
                "verdict": self.verdict.as_dict() if self.verdict else None,
                "served_model": self.model_info or None,
                "monitoring_model": self.monitor_model_info or None,
                "steps": [s.as_dict() for s in self.steps],
                "artifacts": sorted({*self.artifacts, RUN_JSON}),
            }
        )
        self._write(RUN_JSON, record)
        return record


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Fail fast, before anything is written: the workflow runs with this flag so
    # a cron can never quietly publish fixture numbers as if they were data.
    if args.require_eia_key and eia_api_key() is None:
        print(MISSING_KEY_MESSAGE, file=sys.stderr)
        return 2

    record = DailyPipeline(args).run()
    _report(record)
    return 0 if record["status"] == "ok" else 1


def _report(record: dict) -> None:
    print()
    for step in record["steps"]:
        marker = {"ok": "  ", "skipped": "  ", "degraded": " ~", "failed": "!!"}[step["status"]]
        print(f"{marker} {step['step']:<10} {step['status']:<9} {step['seconds']:>6.1f}s")

    verdict = record.get("verdict")
    if verdict:
        print()
        print(f"drift verdict: {verdict['action'].upper()} ({verdict['rule']})")
    print(f"artifacts:     {', '.join(record['artifacts'])}")

    if not record["is_real"]:
        print()
        print("!!! EVERY NUMBER IN THIS RUN IS FIXTURE-DERIVED, NOT A RESULT.")
        print(f"!!! {SYNTHETIC_WARNING}")


if __name__ == "__main__":
    sys.exit(main())
