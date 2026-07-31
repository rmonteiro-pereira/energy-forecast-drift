"""`uv run python -m models` — walk-forward backtest of the seasonal-naive baseline.

Writes `metrics/baseline.json` (the committed artifact every future model is
measured against) and `metrics/baseline_table.md` (the README table).

Data source resolution (`--source auto`, the default):
  1. real EIA demand from the lake, if `python -m ingest` has stored any;
  2. otherwise the **synthetic fixture**, loudly labelled as such in every
     artifact, so the pipeline stays runnable while the API key is pending.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from features import panel as panel_mod
from ingest.config import METRICS_DIR
from models import backtest, baseline, fixtures
from models.data import SYNTHETIC_WARNING, NoRealDataError, resolve_panel

log = logging.getLogger("models")

BASELINE_JSON = METRICS_DIR / "baseline.json"
BASELINE_TABLE = METRICS_DIR / "baseline_table.md"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="models", description=__doc__)
    p.add_argument(
        "--source",
        choices=["auto", "real", "synthetic"],
        default="auto",
        help="which demand series to backtest (default: auto)",
    )
    p.add_argument("--weeks", type=int, default=backtest.DEFAULT_WEEKS)
    p.add_argument("--max-horizon", type=int, default=max(backtest.DEFAULT_HORIZONS))
    p.add_argument("--cutoff-hour", type=int, default=backtest.DEFAULT_CUTOFF_HOUR)
    p.add_argument(
        "--fixture-days",
        type=int,
        default=200,
        help="length of the synthetic fixture when it is used (default: 200)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=METRICS_DIR,
        help="where to write the artifacts (default: metrics/); point elsewhere "
        "for smoke tests so the committed baseline is not overwritten",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def resolve_series(args: argparse.Namespace) -> tuple[pd.DataFrame, dict]:
    """Return the modelling panel plus a provenance block for the artifact."""
    try:
        return resolve_panel(args.source, fixture_days=args.fixture_days)
    except NoRealDataError as exc:
        raise SystemExit(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    panel, provenance = resolve_series(args)
    horizons = tuple(range(1, args.max_horizon + 1))

    result = backtest.run(
        panel[panel_mod.DEMAND_COLUMN],
        lambda history, targets, cutoff: baseline.predict(history, targets, cutoff),
        horizons=horizons,
        weeks=args.weeks,
        cutoff_hour=args.cutoff_hour,
    )

    artifact = build_artifact(args, panel, provenance, result)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / BASELINE_JSON.name
    table_path = out_dir / BASELINE_TABLE.name
    json_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    table_path.write_text(render_table_doc(artifact, result), encoding="utf-8")

    if not provenance["is_real"]:
        log.warning("!!! %s", SYNTHETIC_WARNING)

    print()
    print(backtest.markdown_table(result.by_horizon))
    print()
    print(
        f"overall MAE={result.overall['mae']:,.0f} MWh  "
        f"MAPE={result.overall['mape_pct']:.2f}%  "
        f"({len(result.folds)} folds x {len(horizons)} horizons)"
    )
    print(f"wrote {json_path} and {table_path}")
    return 0


def build_artifact(
    args: argparse.Namespace,
    panel: pd.DataFrame,
    provenance: dict,
    result: backtest.BacktestResult,
) -> dict:
    by_horizon = [
        {
            "horizon_h": int(r.horizon_h),
            "mae": round(float(r.mae), 2),
            "mape_pct": round(float(r.mape_pct), 4),
            "rmse": round(float(r.rmse), 2),
            "bias": round(float(r.bias), 2),
            "n": int(r.n),
        }
        for r in result.by_horizon.itertuples(index=False)
    ]

    return {
        "milestone": "M1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        # Provenance is hoisted to the top level, mirroring every other artifact.
        # It is also still nested under `data`, which is where the richer block
        # (seed, anchor, panel shape) lives. Duplicating the two fields is cheap;
        # the alternative is a consumer reading `artifact["is_real"]`, getting
        # `None` because this one artifact happens to nest it, and treating the
        # falsy result as "not synthetic" by accident. Every published artifact
        # answers `is_real` at the same key -- that is the contract, and
        # `tests/test_artifacts.py` enforces it.
        "is_real": provenance["is_real"],
        "warning": None if provenance["is_real"] else SYNTHETIC_WARNING,
        "model": {
            "name": baseline.NAME,
            "description": "demand at the same hour, 7 days earlier",
            "season_hours": baseline.SEASON_HOURS,
        },
        "data": {**provenance, "panel": panel_mod.describe_panel(panel)},
        "backtest": {
            "protocol": "walk-forward, daily cutoffs, no temporal leakage",
            "weeks": args.weeks,
            "cutoff_hour_utc": args.cutoff_hour,
            "folds": len(result.folds),
            "skipped_folds": result.skipped_folds,
            "horizons_h": [int(h) for h in result.by_horizon["horizon_h"]],
            "first_cutoff_utc": result.folds[0].isoformat() if result.folds else None,
            "last_cutoff_utc": result.folds[-1].isoformat() if result.folds else None,
            "warnings": result.warnings[:20],
        },
        "metrics": {
            "units": {"mae": "MWh", "rmse": "MWh", "bias": "MWh", "mape_pct": "%"},
            "overall": {
                k: round(v, 4) if isinstance(v, float) else v for k, v in result.overall.items()
            },
            "by_horizon": by_horizon,
        },
    }


def render_table_doc(artifact: dict, result: backtest.BacktestResult) -> str:
    header = "# Baseline — seasonal naive (same hour, 7 days earlier)\n\n"
    if not artifact["data"]["is_real"]:
        header += f"> ⚠️ **{fixtures.SYNTHETIC_LABEL}.** {SYNTHETIC_WARNING}\n\n"

    meta = (
        f"- generated: `{artifact['generated_at_utc']}`\n"
        f"- source: `{artifact['data']['kind']}`\n"
        f"- folds: {artifact['backtest']['folds']} daily cutoffs over "
        f"{artifact['backtest']['weeks']} weeks\n"
        f"- overall: **MAE {result.overall['mae']:,.0f} MWh**, "
        f"MAPE {result.overall['mape_pct']:.2f}%\n\n"
    )
    return header + meta + backtest.markdown_table(result.by_horizon) + "\n"


if __name__ == "__main__":
    sys.exit(main())
