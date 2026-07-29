"""`uv run python -m drift.run --out metrics/drift.json` — the M4 entrypoint.

What it does, in order:

1. resolves the modelling panel exactly like `models.train` does — real lake if
   the EIA leg has stored anything, otherwise the seeded synthetic fixture, with
   the same `"is_real"` flag and the same warning attached (`models.data`);
2. cuts it into train / reference / current and scores the last two with a
   booster fitted on the train window alone (`drift.windows`);
3. runs all four detectors — feature, target, prediction, performance —
   (`drift.detectors`) and, when Evidently is installed, an independent report
   next to them (`drift.evidently_report`);
4. collapses the four into one structured retrain verdict (`drift.trigger`);
5. writes `metrics/drift.json` and `metrics/drift_summary.md`.

The exit code is 0 whether or not drift was found: drift is a *result*, not a
failure. Use `--fail-on-retrain` to make a CI job red when the verdict says to
retrain.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from drift import detectors, evidently_report, simulate, trigger
from drift.config import DEFAULT_CURRENT_DAYS, DEFAULT_REFERENCE_DAYS, DriftThresholds, Severity
from drift.windows import NotEnoughHistoryError, ScoredWindows, build_windows
from features import panel as panel_mod
from ingest.config import METRICS_DIR, REPO_ROOT
from models import lgbm as lgbm_mod
from models.data import SYNTHETIC_WARNING, NoRealDataError, resolve_panel

log = logging.getLogger("drift.run")

DRIFT_JSON = METRICS_DIR / "drift.json"
DRIFT_SUMMARY = METRICS_DIR / "drift_summary.md"

# Evidently's HTML report is ~5 MB of inlined plotly. It is a local artifact to
# look at, not a published one, so it goes to a gitignored `reports/` directory
# rather than to `metrics/` — which stays small, committed and machine-readable.
REPORTS_DIR = REPO_ROOT / "reports"
EVIDENTLY_HTML = REPORTS_DIR / "drift_evidently.html"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="drift.run", description=__doc__)
    p.add_argument("--source", choices=["auto", "real", "synthetic"], default="auto")
    p.add_argument("--fixture-days", type=int, default=200)
    p.add_argument("--reference-days", type=int, default=DEFAULT_REFERENCE_DAYS)
    p.add_argument("--current-days", type=int, default=DEFAULT_CURRENT_DAYS)
    p.add_argument("--max-horizon", type=int, default=24)
    p.add_argument("--train-stride-hours", type=int, default=6)
    p.add_argument("--num-boost-round", type=int, default=lgbm_mod.DEFAULT_NUM_BOOST_ROUND)
    p.add_argument(
        "--out",
        type=Path,
        default=DRIFT_JSON,
        help=f"where to write the drift artifact (default: {DRIFT_JSON.name} in metrics/)",
    )
    p.add_argument(
        "--no-evidently",
        action="store_true",
        help="skip the Evidently second opinion (it is optional and slow-ish)",
    )
    p.add_argument(
        "--evidently-html",
        type=Path,
        default=EVIDENTLY_HTML,
        help=f"where to write Evidently's HTML report (default: {EVIDENTLY_HTML.name} "
        "in the gitignored reports/ directory — it is ~5MB of inlined plotly)",
    )
    p.add_argument(
        "--no-html",
        action="store_true",
        help="compute the Evidently summary but do not write its HTML report",
    )
    p.add_argument(
        "--simulate-shift",
        type=float,
        default=None,
        metavar="MW",
        help=(
            "DEMO ONLY: inject a demand level shift of this many MW over the current "
            "window before scoring, to show the alarm firing. The artifact is stamped "
            "`simulated_shift` so it can never be mistaken for an observed episode."
        ),
    )
    p.add_argument(
        "--fail-on-retrain",
        action="store_true",
        help="exit 1 when the verdict is `retrain` (for use as a CI gate)",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def build_artifact(
    windows: ScoredWindows,
    sections: dict[str, detectors.DriftSection],
    verdict: trigger.RetrainVerdict,
    thresholds: DriftThresholds,
    provenance: dict,
    panel: pd.DataFrame,
    evidently: dict,
    shift: dict | None = None,
) -> dict:
    """The full `metrics/drift.json` payload."""
    artifact = {
        "milestone": "M4",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        # Mirrored at the top level as well as inside `data` so no consumer of
        # this file can miss it.
        "is_real": provenance["is_real"],
        "warning": provenance["warning"],
        "verdict": verdict.as_dict(),
        "thresholds": thresholds.as_dict(),
        "windows": windows.split,
        "data": {**provenance, "panel": panel_mod.describe_panel(panel)},
        "drift": {name: section.as_dict() for name, section in sections.items()},
        "timeline": {
            "description": (
                "PSI of a trailing 7-day window against the whole reference window, "
                "one point per day — the 'since when' the four sections above cannot answer"
            ),
            "trailing_window_days": 7,
            "points": detectors.drift_timeline(windows, thresholds),
        },
        "evidently": evidently,
    }
    if shift is not None:
        artifact["simulated_shift"] = shift
    return artifact


def render_summary(artifact: dict) -> str:
    """A short markdown digest — what a human reads before opening the JSON."""
    verdict = artifact["verdict"]
    icon = {"ok": "🟢", "warn": "🟡", "alert": "🔴"}
    # The verdict icon tracks the *action*, not the worst severity: a red section
    # with a `watch` action is the normal, healthy case for a leading indicator.
    action_icon = {"retrain": "🔴", "watch": "🟡", "none": "🟢"}

    lines = ["# M4 — drift report\n"]
    if not artifact["is_real"]:
        lines.append(f"> ⚠️ **SYNTHETIC — NOT REAL DATA.** {artifact['warning']}\n")
    if "simulated_shift" in artifact:
        shift = artifact["simulated_shift"]
        lines.append(
            f"> 🧪 **SIMULATED DRIFT EPISODE.** A `{shift['kind']}` of "
            f"{shift['demand_offset_mw']:+,.0f} MW was injected from "
            f"`{shift['start_utc']}` to demonstrate the alarm. Not an observed episode.\n"
        )

    windows = artifact["windows"]
    lines.append(
        f"- generated: `{artifact['generated_at_utc']}`\n"
        f"- source: `{artifact['data']['kind']}`\n"
        f"- reference: `{windows['reference_start_utc']}` → `{windows['current_start_utc']}` "
        f"({windows['rows']['reference']:,} rows)\n"
        f"- current: `{windows['current_start_utc']}` → `{windows['panel_end_utc']}` "
        f"({windows['rows']['current']:,} rows)\n"
    )

    lines.append(
        f"\n## Verdict: {action_icon.get(verdict['action'], '')} "
        f"**{verdict['action'].upper()}** (`{verdict['rule']}`)\n\n"
        f"{verdict['rationale']}\n\n"
        f"Worst signal severity: `{verdict['severity']}`. "
        f"Retrain now? **{'yes' if verdict['should_retrain'] else 'no'}**.\n"
    )

    lines.append("\n| Drift type | Severity | Summary |\n|---|---|---|")
    for name, section in artifact["drift"].items():
        lines.append(
            f"| {name} | {icon.get(section['severity'], '')} {section['severity']} "
            f"| {section['summary']} |"
        )

    feature = artifact["drift"]["feature"]
    if feature.get("columns"):
        lines.append("\n### Worst features by PSI\n")
        lines.append("| Feature | PSI | KS p | Severity |\n|---|---:|---:|---|")
        for column in feature["columns"][:8]:
            lines.append(
                f"| `{column['column']}` | {column['psi']['psi']:.4f} "
                f"| {column['ks']['p_value']:.2e} | {column['severity']} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        panel, provenance = resolve_panel(args.source, fixture_days=args.fixture_days)
    except NoRealDataError as exc:
        raise SystemExit(str(exc)) from exc

    shift = None
    if args.simulate_shift is not None:
        panel, spec = simulate.inject_shift(
            panel,
            days_before_end=args.current_days,
            demand_offset_mw=args.simulate_shift,
            note="injected by `--simulate-shift` to demonstrate the retrain trigger",
        )
        shift = spec.as_dict()
        log.warning(
            "!!! SIMULATED SHIFT of %s MW injected — this run is a DEMO, not an observation.",
            f"{args.simulate_shift:+,.0f}",
        )

    thresholds = DriftThresholds.from_env()
    try:
        windows = build_windows(
            panel,
            reference_days=args.reference_days,
            current_days=args.current_days,
            horizons=tuple(range(1, args.max_horizon + 1)),
            stride_hours=args.train_stride_hours,
            num_boost_round=args.num_boost_round,
        )
    except NotEnoughHistoryError as exc:
        raise SystemExit(str(exc)) from exc

    sections = detectors.run_all(windows, thresholds)
    verdict = trigger.evaluate(sections, thresholds)

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.no_evidently:
        evidently = {"status": "skipped", "reason": "--no-evidently"}
    else:
        html_path = None if args.no_html else args.evidently_html
        evidently = evidently_report.build_report(windows, html_path=html_path)

    artifact = build_artifact(
        windows, sections, verdict, thresholds, provenance, panel, evidently, shift
    )
    out_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    summary_path = out_path.parent / DRIFT_SUMMARY.name
    summary_path.write_text(render_summary(artifact), encoding="utf-8")

    _report(artifact)
    print(f"wrote {out_path} and {summary_path}")

    if args.fail_on_retrain and verdict.should_retrain:
        log.error("Verdict is RETRAIN and --fail-on-retrain was passed.")
        return 1
    return 0


def _report(artifact: dict) -> None:
    verdict = artifact["verdict"]
    print()
    for name, section in artifact["drift"].items():
        marker = "  " if section["severity"] == Severity.OK.value else "!!"
        print(f"{marker} {name:<12} {section['severity']:<6} {section['summary']}")
    print()
    print(f"verdict: {verdict['action'].upper()} ({verdict['rule']}) — {verdict['rationale']}")
    if not artifact["is_real"]:
        print()
        print("!!! THIS DRIFT REPORT IS FIXTURE-DERIVED, NOT A RESULT.")
        print(f"!!! {SYNTHETIC_WARNING}")


if __name__ == "__main__":
    sys.exit(main())
