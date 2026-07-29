"""`uv run python -m models.train` — LightGBM vs the baseline, tracked in MLflow (M2 + M3).

What this does, in order:

1. resolves the modelling panel (real lake if it has data, otherwise the seeded
   synthetic fixture — see `models.data`);
2. runs **the existing walk-forward backtest**, unchanged, twice: once for the
   seasonal-naive baseline and once for the global LightGBM. Same folds, same
   horizons, same protocol — that is the only way the comparison means anything;
3. logs both to MLflow (sqlite backend), refits LightGBM on the whole panel and
   registers it, promoting it to `@champion` **only if it actually beat the
   baseline**;
4. writes `metrics/model.json` + `metrics/model_table.md`, carrying the same
   `"is_real": false` flag and synthetic warning as the M1 baseline artifact.

The MAE numbers this prints are **not results** while the fixture is in play.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from features import build as build_mod
from features import panel as panel_mod
from ingest.config import METRICS_DIR
from models import backtest, baseline, lgbm, tracking
from models.data import SYNTHETIC_WARNING, NoRealDataError, resolve_panel

log = logging.getLogger("models.train")

MODEL_JSON = METRICS_DIR / "model.json"
MODEL_TABLE = METRICS_DIR / "model_table.md"

# What goes in the committed artifact instead of an absolute local path — the
# database lives beside the repo and is gitignored, so its full path is noise.
TRACKING_BACKEND_LABEL = "sqlite:///mlflow.db (local, gitignored)"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="models.train", description=__doc__)
    p.add_argument("--source", choices=["auto", "real", "synthetic"], default="auto")
    p.add_argument("--weeks", type=int, default=backtest.DEFAULT_WEEKS)
    p.add_argument("--max-horizon", type=int, default=max(backtest.DEFAULT_HORIZONS))
    p.add_argument("--cutoff-hour", type=int, default=backtest.DEFAULT_CUTOFF_HOUR)
    p.add_argument("--fixture-days", type=int, default=200)
    p.add_argument(
        "--train-stride-hours",
        type=int,
        default=6,
        help="spacing of the forecast origins used for training rows (default: 6)",
    )
    p.add_argument("--num-boost-round", type=int, default=lgbm.DEFAULT_NUM_BOOST_ROUND)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=METRICS_DIR,
        help="where to write the artifacts (default: metrics/)",
    )
    p.add_argument(
        "--no-mlflow",
        action="store_true",
        help="skip tracking and the registry; just score and write the artifact",
    )
    p.add_argument("--experiment", default=tracking.EXPERIMENT_NAME)
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def compare(
    base: backtest.BacktestResult,
    challenger: backtest.BacktestResult,
) -> dict:
    """Head-to-head on identical folds: overall delta plus a per-horizon column."""
    merged = base.by_horizon.merge(
        challenger.by_horizon, on="horizon_h", suffixes=("_baseline", "_model")
    )
    merged["mae_delta"] = merged["mae_model"] - merged["mae_baseline"]
    merged["mae_delta_pct"] = 100.0 * merged["mae_delta"] / merged["mae_baseline"]

    base_mae = base.overall["mae"]
    model_mae = challenger.overall["mae"]
    return {
        "mae_delta": round(model_mae - base_mae, 2),
        "mae_delta_pct": round(100.0 * (model_mae - base_mae) / base_mae, 2),
        "mape_delta_pct_points": round(
            challenger.overall["mape_pct"] - base.overall["mape_pct"], 4
        ),
        "horizons_won": int((merged["mae_delta"] < 0).sum()),
        "horizons_total": len(merged),
        "by_horizon": [
            {
                "horizon_h": int(r.horizon_h),
                "baseline_mae": round(float(r.mae_baseline), 2),
                "model_mae": round(float(r.mae_model), 2),
                "mae_delta": round(float(r.mae_delta), 2),
                "mae_delta_pct": round(float(r.mae_delta_pct), 2),
            }
            for r in merged.itertuples(index=False)
        ],
    }


def _by_horizon_records(result: backtest.BacktestResult) -> list[dict]:
    return [
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


def _rounded(overall: dict) -> dict:
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in overall.items()}


def build_artifact(
    args: argparse.Namespace,
    panel: pd.DataFrame,
    provenance: dict,
    base: backtest.BacktestResult,
    challenger: backtest.BacktestResult,
    model: lgbm.WalkForwardLightGBM,
    registry: dict,
    importances: list[dict],
) -> dict:
    comparison = compare(base, challenger)
    return {
        "milestone": "M2+M3",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        # Mirrored at the top level as well as inside `data` so no consumer of
        # this file can miss it.
        "is_real": provenance["is_real"],
        "warning": provenance["warning"],
        "models": {
            "baseline": {
                "name": baseline.NAME,
                "description": "demand at the same hour, 7 days earlier",
                "season_hours": baseline.SEASON_HOURS,
            },
            "challenger": {
                "name": lgbm.NAME,
                "description": (
                    "one global LightGBM over all horizons; horizon is a feature "
                    "(direct multi-horizon, no recursion)"
                ),
                "library": "lightgbm",
                "params": {**lgbm.DEFAULT_PARAMS, **model.params},
                "num_boost_round": args.num_boost_round,
                "train_origin_stride_hours": args.train_stride_hours,
                "refits": model.fits,
                "train_rows_last_fold": model.last_train_rows,
                "n_features": len(build_mod.FEATURE_COLUMNS),
                "features": list(build_mod.FEATURE_COLUMNS),
            },
        },
        "data": {**provenance, "panel": panel_mod.describe_panel(panel)},
        "backtest": {
            "protocol": "walk-forward, daily cutoffs, no temporal leakage",
            "note": "identical folds and horizons for both models (models.backtest)",
            "weeks": args.weeks,
            "cutoff_hour_utc": args.cutoff_hour,
            "folds": len(challenger.folds),
            "skipped_folds": challenger.skipped_folds,
            "horizons_h": [int(h) for h in challenger.by_horizon["horizon_h"]],
            "first_cutoff_utc": challenger.folds[0].isoformat() if challenger.folds else None,
            "last_cutoff_utc": challenger.folds[-1].isoformat() if challenger.folds else None,
            "warnings": challenger.warnings[:20],
        },
        "metrics": {
            "units": {"mae": "MWh", "rmse": "MWh", "bias": "MWh", "mape_pct": "%"},
            "baseline": {
                "overall": _rounded(base.overall),
                "by_horizon": _by_horizon_records(base),
            },
            "lightgbm": {
                "overall": _rounded(challenger.overall),
                "by_horizon": _by_horizon_records(challenger),
            },
            "comparison": comparison,
        },
        "feature_importance_gain_pct": importances,
        "registry": registry,
    }


def render_table_doc(artifact: dict) -> str:
    comparison = artifact["metrics"]["comparison"]
    header = "# M2 — LightGBM vs the seasonal-naive baseline\n\n"
    if not artifact["is_real"]:
        header += f"> ⚠️ **SYNTHETIC — NOT REAL DATA.** {artifact['warning']}\n\n"

    meta = (
        f"- generated: `{artifact['generated_at_utc']}`\n"
        f"- source: `{artifact['data']['kind']}`\n"
        f"- protocol: {artifact['backtest']['folds']} daily folds x "
        f"{len(artifact['backtest']['horizons_h'])} horizons, identical for both models\n"
        f"- overall MAE: baseline **{artifact['metrics']['baseline']['overall']['mae']:,.0f}** -> "
        f"LightGBM **{artifact['metrics']['lightgbm']['overall']['mae']:,.0f}** MWh "
        f"({comparison['mae_delta_pct']:+.1f}%)\n"
        f"- horizons where LightGBM wins: "
        f"{comparison['horizons_won']}/{comparison['horizons_total']}\n\n"
    )

    lines = [
        "| Horizon (h) | Baseline MAE | LightGBM MAE | Delta | Delta % |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in comparison["by_horizon"]:
        lines.append(
            f"| {row['horizon_h']} | {row['baseline_mae']:,.0f} | {row['model_mae']:,.0f} | "
            f"{row['mae_delta']:+,.0f} | {row['mae_delta_pct']:+.1f} |"
        )
    return header + meta + "\n".join(lines) + "\n"


def _track(
    args: argparse.Namespace, panel, provenance, base, challenger, model
) -> tuple[dict, list]:
    """Log both runs, register the refit booster, promote only a genuine winner."""
    import mlflow

    config = tracking.configure(experiment_name=args.experiment)
    beats_baseline = challenger.overall["mae"] < base.overall["mae"]

    with mlflow.start_run(run_name=f"{lgbm.NAME}-w{args.weeks}") as run:
        mlflow.set_tags(
            {
                "milestone": "M2+M3",
                "protocol": "walk-forward",
                "data_kind": provenance["kind"],
                "is_real": str(provenance["is_real"]).lower(),
            }
        )
        mlflow.log_params(
            {
                "model": lgbm.NAME,
                "weeks": args.weeks,
                "max_horizon": args.max_horizon,
                "cutoff_hour_utc": args.cutoff_hour,
                "train_origin_stride_hours": args.train_stride_hours,
                "num_boost_round": args.num_boost_round,
                "n_features": len(build_mod.FEATURE_COLUMNS),
                "panel_rows": len(panel),
                **{f"lgb_{k}": v for k, v in lgbm.DEFAULT_PARAMS.items()},
            }
        )
        tracking.log_backtest("baseline", base)
        tracking.log_backtest("lightgbm", challenger)
        mlflow.log_metric("mae_delta_vs_baseline", challenger.overall["mae"] - base.overall["mae"])

        booster, design = lgbm.fit_final(
            panel,
            horizons=tuple(range(1, args.max_horizon + 1)),
            num_boost_round=args.num_boost_round,
            train_stride_hours=args.train_stride_hours,
        )
        sample = build_mod.feature_frame(design.tail(200))
        version = tracking.register_model(
            booster,
            sample,
            booster.predict(sample),
            tags={"is_real": provenance["is_real"], "data_kind": provenance["kind"]},
        )
        alias = tracking.CHAMPION_ALIAS if beats_baseline else tracking.CHALLENGER_ALIAS
        tracking.set_alias(version, alias)

        registry = {
            "backend": TRACKING_BACKEND_LABEL,
            "experiment": config.experiment_name,
            "run_id": run.info.run_id,
            "registered_model": tracking.REGISTERED_MODEL_NAME,
            "version": version,
            "alias": alias,
            "uri": tracking.champion_uri(alias),
            "beats_baseline": beats_baseline,
            "promoted": alias == tracking.CHAMPION_ALIAS,
            "note": (
                "mlruns/ and mlflow.db are local run state and are gitignored; "
                "metrics/*.json is the only published surface."
            ),
        }
        mlflow.log_dict(registry, "registry.json")

    return registry, lgbm.importance(booster)


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

    horizons = tuple(range(1, args.max_horizon + 1))
    series = panel[panel_mod.DEMAND_COLUMN]
    run_kwargs = {"horizons": horizons, "weeks": args.weeks, "cutoff_hour": args.cutoff_hour}

    log.info("Scoring the seasonal-naive baseline ...")
    base = backtest.run(series, baseline.predict, **run_kwargs)

    log.info("Scoring LightGBM (refit at every fold cutoff) ...")
    model = lgbm.WalkForwardLightGBM(
        panel=panel,
        horizons=horizons,
        num_boost_round=args.num_boost_round,
        train_stride_hours=args.train_stride_hours,
    )
    challenger = backtest.run(series, model, **run_kwargs)

    if args.no_mlflow:
        registry = {"backend": None, "skipped": True, "reason": "--no-mlflow"}
        booster, _design = lgbm.fit_final(
            panel,
            horizons=horizons,
            num_boost_round=args.num_boost_round,
            train_stride_hours=args.train_stride_hours,
        )
        importances = lgbm.importance(booster)
    else:
        registry, importances = _track(args, panel, provenance, base, challenger, model)

    artifact = build_artifact(
        args, panel, provenance, base, challenger, model, registry, importances
    )

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / MODEL_JSON.name
    table_path = out_dir / MODEL_TABLE.name
    json_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    table_path.write_text(render_table_doc(artifact), encoding="utf-8")

    _report(artifact, provenance)
    print(f"wrote {json_path} and {table_path}")
    return 0


def _report(artifact: dict, provenance: dict) -> None:
    comparison = artifact["metrics"]["comparison"]
    base_mae = artifact["metrics"]["baseline"]["overall"]["mae"]
    model_mae = artifact["metrics"]["lightgbm"]["overall"]["mae"]

    print()
    print(render_table_doc(artifact).split("\n\n", 2)[-1])
    print(
        f"seasonal naive  MAE {base_mae:>10,.0f} MWh   "
        f"MAPE {artifact['metrics']['baseline']['overall']['mape_pct']:.2f}%"
    )
    print(
        f"LightGBM        MAE {model_mae:>10,.0f} MWh   "
        f"MAPE {artifact['metrics']['lightgbm']['overall']['mape_pct']:.2f}%"
    )
    print(
        f"delta           MAE {comparison['mae_delta']:>+10,.0f} MWh   "
        f"({comparison['mae_delta_pct']:+.2f}%), "
        f"LightGBM wins {comparison['horizons_won']}/{comparison['horizons_total']} horizons"
    )
    if not provenance["is_real"]:
        print()
        print("!!! THIS DELTA IS FIXTURE-DERIVED, NOT A RESULT.")
        print(f"!!! {SYNTHETIC_WARNING}")


if __name__ == "__main__":
    sys.exit(main())
