"""`uv run python -m foundation` — the lane's dispatch run.

Until this file existed, `foundation.compare.score_arm` and `build_artifact`
were called by nothing but tests. The lane had every gate, every contract and
every arm, and no command: "Phase 6 is a dispatch step" named an action nobody
could take. This is that action.

What it does, in the order the order matters:

1. **Resolve the panel** through `models.data`, so `is_real` and its warning are
   decided in the same place as for every other artifact in the repository.
2. **Derive the cutoff candidates once**, from the raw index, and hand the same
   list to every arm. Deriving them per arm is how "the same folds" becomes a
   sentence instead of a fact.
3. **Guard contiguity once**, before the arms fork (G2). Inside an adapter the
   same missing hour reaches the foundation model interpolated and the GBM as
   NaN, and the arms are then scored on different data.
4. **Score each arm**, metering `fit`, `infer` and `load` on three lines that are
   never summed, and running the composition, params and cadence gates against
   the *trained* object rather than against the caller's declaration.
5. **Probe for foresight** (G3), rebuilding each arm from the perturbed series.
6. **Assemble**, which aligns the fold sets (G1), takes the interval over origins
   (G10) and refuses on any gate rather than publishing (G7).
7. **Write** — and refuse to write a fixture-derived artifact to the published
   path, because `metrics/foundation.json` is defined as real or absent.

Two threading facts are enforced rather than assumed. `models/lgbm.py` freezes
`num_threads: 0` — every core — into its published parameters, and
`params={"num_threads": 1}` alone does *not* serialise the work: OpenMP threads
keep spinning and the measured CPU:wall ratio was 1.38, impossible for one
thread. Only `OMP_NUM_THREADS` in the environment brings it to 0.99. So the run
refuses to start when the environment and `--n-threads` disagree, instead of
publishing a cost table that quietly measures a different machine.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from features import panel as panel_mod
from foundation import compare, cost, guards, imputation, stub
from ingest.config import METRICS_DIR
from models import arms as arms_mod
from models import backtest, baseline, lgbm
from models.data import NoRealDataError, resolve_panel

log = logging.getLogger("foundation")

PUBLISHED = METRICS_DIR / "foundation.json"
#: The only provenance the published path accepts. Mirrors
#: `tests/test_lane_artifact.py::test_metrics_foundation_json_is_real_or_absent`
#: — the gate and the writer agree by construction rather than by discipline.
PUBLISHABLE_KIND = "eia_api_v2"

#: The ladder, in the order the RFC reports it. `lgbm_17_demand_only` is the
#: verdict's denominator; `lgbm_12_no_calendar` is the information floor.
DEFAULT_ARMS = ("lgbm_17_demand_only", "lgbm_12_no_calendar")


class DispatchError(RuntimeError):
    """The run cannot be trusted to produce a number. Not a gate refusal."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="foundation", description=__doc__)
    p.add_argument("--source", choices=["auto", "real", "synthetic"], default="auto")
    p.add_argument("--fixture-days", type=int, default=200)
    p.add_argument("--weeks", type=int, default=backtest.DEFAULT_WEEKS)
    p.add_argument("--max-horizon", type=int, default=max(backtest.DEFAULT_HORIZONS))
    p.add_argument("--cutoff-hour", type=int, default=backtest.DEFAULT_CUTOFF_HOUR)
    p.add_argument(
        "--arms",
        default=",".join(DEFAULT_ARMS),
        help="comma-separated arm ids, or 'all' for the whole ladder "
        f"(default: {','.join(DEFAULT_ARMS)})",
    )
    p.add_argument(
        "--tsfm",
        choices=["chronos", "stub", "none"],
        default="stub",
        help="the zero-shot arm. 'chronos' needs the foundation extra and a "
        "network; 'stub' proves the contract and nothing about any model",
    )
    p.add_argument(
        "--context-hours",
        type=int,
        default=None,
        help="context handed to the TSFM (default: the GBM's deepest reach)",
    )
    p.add_argument("--n-threads", type=int, default=1)
    p.add_argument(
        "--probe-gbm-folds",
        type=int,
        default=3,
        help="how many folds the foresight probe covers on the GBM arms. Full "
        "coverage costs two extra refit-per-fold backtests per fold; the "
        "subset is declared rather than silently sampled (default: 3)",
    )
    p.add_argument(
        "--probe-tsfm-folds",
        type=int,
        default=0,
        help="the same for the zero-shot arm, which has no leakage assertion of "
        "its own; 0 means every fold (default: 0)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"where to write (default: {PUBLISHED}, which only accepts a real run)",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args(argv)


def _assert_threads_are_pinned(n_threads: int) -> None:
    """The cost table is a statement about a machine, so the machine is pinned."""
    declared = os.environ.get("OMP_NUM_THREADS")
    if declared != str(n_threads):
        raise DispatchError(
            f"OMP_NUM_THREADS={declared!r} but --n-threads={n_threads}. "
            "`params={'num_threads': 1}` alone leaves OpenMP threads spinning "
            "(measured CPU:wall 1.38, impossible for one thread), so the cost "
            f"lines would describe a machine nobody configured. Re-run with "
            f"OMP_NUM_THREADS={n_threads}."
        )


def _resolve_arm_ids(spec: str) -> list[str]:
    if spec.strip() == "all":
        return list(arms_mod.ARMS)
    ids = [a.strip() for a in spec.split(",") if a.strip()]
    unknown = [a for a in ids if a not in arms_mod.ARMS]
    if unknown:
        raise DispatchError(f"unknown arm id(s) {unknown}; known: {sorted(arms_mod.ARMS)}")
    if not ids:
        raise DispatchError("no arms requested: the artifact would be vacuous")
    return ids


def _guarded_panel(panel: pd.DataFrame, guarded: pd.Series) -> pd.DataFrame:
    """The panel the GBM arms see, carrying exactly the guarded demand series.

    Reindexing rather than merging: an hour the guard fabricated has no weather
    reading and must arrive as NaN, not as a neighbour's temperature. The GBM
    consumes NaN natively; inventing a covariate to go with an invented demand
    value would be the second fabrication hiding behind the first.
    """
    out = panel.reindex(guarded.index)
    out[panel_mod.DEMAND_COLUMN] = guarded
    return out


def _training_hours(series: pd.Series, fit_at: pd.Timestamp) -> int:
    """Hours of in-domain data whose label was observable at the last fit.

    This is what separates `lgbm_12_frozen` from the same arm refit: the frozen
    arm is not a different model, it is the same model with months less data.
    Reporting the gap as a field is the difference between a descriptive arm and
    a rigged denominator.
    """
    return int((series.index < fit_at).sum())


def _score_gbm_arm(
    arm_id: str,
    panel: pd.DataFrame,
    guarded: pd.Series,
    cutoffs: list[pd.Timestamp],
    horizons: tuple[int, ...],
    n_threads: int,
) -> compare.ArmRun:
    spec = arms_mod.ARMS[arm_id]
    freeze_at = cutoffs[0] if spec.frozen else None
    declared = {**lgbm.DEFAULT_PARAMS, "num_threads": n_threads}

    model = lgbm.WalkForwardLightGBM(
        panel,
        horizons=horizons,
        params={"num_threads": n_threads},
        drop_features=spec.drop_features,
        freeze_at=freeze_at,
    )

    meter = cost.CostMeter()
    with meter.timing("infer"):
        result = backtest.run(guarded, model, horizons=horizons, cutoffs=cutoffs)

    # The refit happens inside the call metered as inference — there is no
    # instant at which a caller could start a `fit` timer, which is why
    # `WalkForwardLightGBM` accumulates its own. Move it across rather than
    # letting one line carry both: the refit is the GBM's whole cost.
    meter.infer_cpu_s = max(0.0, meter.infer_cpu_s - model.fit_cpu_s)
    meter.fit_cpu_s = model.fit_cpu_s

    if model.last_booster is None:  # pragma: no cover - backtest.run raises first
        raise DispatchError(f"{arm_id}: scored without ever fitting a booster")
    features = arms_mod.assert_composition(arm_id, model.train_design, spec.drop_features)
    arms_mod.assert_params(arm_id, model.last_booster, declared)

    fit_at = freeze_at if freeze_at is not None else cutoffs[-1]
    return compare.ArmRun(
        arm_id=arm_id,
        result=result,
        cost=meter.block(len(result.predictions)),
        features=features,
        refits=model.fits,
        fit_anchor_utc=freeze_at.isoformat() if freeze_at is not None else None,
        params=declared,
        in_domain_training_hours=_training_hours(guarded, fit_at),
    )


def _zero_shot(kind: str, context_hours: int | None):
    """Return `(arm_id, predict_fn, make_arm, weights, context_hours, load_cpu_s)`."""
    meter = cost.CostMeter()
    if kind == "stub":
        return (
            "stub_zero_shot",
            stub.predict,
            stub.make_arm,
            None,
            stub.SEASON_OFFSET,
            meter,
        )

    # Imported here, not at module scope: this module has to stay importable in
    # the CI job, which installs no torch. The adapter is torch-free on import;
    # `load()` is not.
    from foundation import tsfm

    hours = context_hours or tsfm.MIN_CONTEXT_HOURS
    # `WEIGHTS` mixes strings, ints and bools, so its values type as `object`.
    # Narrowed here rather than loosened at the dataclass: the revision is the
    # one field that decides *which weights ran*, and it goes into the artifact.
    revision = str(tsfm.WEIGHTS["revision"])
    arm = tsfm.ChronosArm(revision=revision, context_hours=hours)
    with meter.timing("load"):
        arm.load()
    return (
        f"chronos_bolt@ctx{hours}",
        arm,
        tsfm.make_arm_factory(revision=revision, context_hours=hours),
        dict(tsfm.WEIGHTS),
        hours,
        meter,
    )


def _probe(make_arm, series, cutoffs, horizons, folds: int, arm_id: str) -> dict:
    """G3 on a declared subset. `folds <= 0` means every fold."""
    sample = None if folds <= 0 else list(cutoffs[:folds])
    report = guards.foresight_probe(make_arm, series, cutoffs, horizons=horizons, sample=sample)
    guards.assert_no_foresight(arm_id, report)
    return {**report, "coverage": "all" if sample is None else f"{len(sample)}/{len(cutoffs)}"}


def run_lane(args: argparse.Namespace) -> dict:
    _assert_threads_are_pinned(args.n_threads)
    arm_ids = _resolve_arm_ids(args.arms)
    horizons = tuple(range(1, args.max_horizon + 1))

    panel, provenance = resolve_panel(args.source, fixture_days=args.fixture_days)
    raw = panel[panel_mod.DEMAND_COLUMN].dropna().sort_index()

    cutoffs = backtest.make_cutoffs(
        pd.DatetimeIndex(raw.index), args.weeks, horizons, args.cutoff_hour, min_history_hours=168
    )
    if not cutoffs:
        raise DispatchError(
            f"no cutoff candidates over {args.weeks} week(s) from {len(raw)} hour(s) of demand"
        )
    log.info("%d cutoff candidate(s), %s .. %s", len(cutoffs), cutoffs[0], cutoffs[-1])

    guarded, contiguity = guards.guard_contiguity(raw, cutoffs)
    gbm_panel = _guarded_panel(panel, guarded)
    log.info("contiguity: %s", contiguity)

    runs: dict[str, compare.ArmRun] = {}
    foresight: dict[str, dict] = {}

    # The seasonal naive is scored first and unconditionally, because Clause 1b
    # charges an arm's unscorable fold the naive's error *on that fold* — so the
    # naive is not one arm among several here, it is the imputation source, and
    # without it the verdict could only come out of the intersection. It is also
    # the trivial floor the ladder is read against, which is why it is published
    # as an arm rather than hidden as machinery.
    log.info("scoring %s", imputation.FILLER_ARM)
    naive_meter = cost.CostMeter()
    with naive_meter.timing("infer"):
        naive_result = backtest.run(guarded, baseline.predict, horizons=horizons, cutoffs=cutoffs)
    runs[imputation.FILLER_ARM] = compare.ArmRun(
        arm_id=imputation.FILLER_ARM,
        result=naive_result,
        cost=naive_meter.block(len(naive_result.predictions)),
        features=[],
        refits=0,
        fit_anchor_utc=None,
        params={},
        in_domain_training_hours=0,
    )
    foresight[imputation.FILLER_ARM] = _probe(
        lambda _s: baseline.predict,
        guarded,
        cutoffs,
        horizons,
        args.probe_gbm_folds,
        imputation.FILLER_ARM,
    )

    for arm_id in arm_ids:
        log.info("scoring %s", arm_id)
        runs[arm_id] = _score_gbm_arm(arm_id, gbm_panel, guarded, cutoffs, horizons, args.n_threads)
        foresight[arm_id] = _probe(
            lambda s, _id=arm_id: lgbm.WalkForwardLightGBM(
                _guarded_panel(panel, s),
                horizons=horizons,
                params={"num_threads": args.n_threads},
                drop_features=arms_mod.ARMS[_id].drop_features,
                freeze_at=cutoffs[0] if arms_mod.ARMS[_id].frozen else None,
            ),
            guarded,
            cutoffs,
            horizons,
            args.probe_gbm_folds,
            arm_id,
        )

    if args.tsfm != "none":
        arm_id, predict_fn, make_arm, weights, context_hours, meter = _zero_shot(
            args.tsfm, args.context_hours
        )
        log.info("scoring %s", arm_id)
        with meter.timing("infer"):
            result = backtest.run(guarded, predict_fn, horizons=horizons, cutoffs=cutoffs)
        runs[arm_id] = compare.ArmRun(
            arm_id=arm_id,
            result=result,
            cost=meter.block(len(result.predictions)),
            features=[],
            refits=0,
            fit_anchor_utc=None,
            params={},
            in_domain_training_hours=0,
            context_hours=context_hours,
            weights=weights,
        )
        foresight[arm_id] = _probe(
            make_arm, guarded, cutoffs, horizons, args.probe_tsfm_folds, arm_id
        )

    return compare.build_artifact(
        runs,
        cutoff_candidates=cutoffs,
        contiguity=contiguity,
        is_real=provenance["is_real"],
        data_kind=provenance["kind"],
        n_threads=args.n_threads,
        warning=provenance.get("warning"),
        foresight=foresight,
    )


def refuse_to_publish_a_fixture(path: Path, artifact: dict) -> None:
    """`metrics/foundation.json` is real or absent — enforced at the writer.

    Stated as a refusal here as well as a test because the test can only notice
    after the file is committed, and the person who would be misled by a
    synthetic artifact at the published path is the same person who ran this
    with `--source synthetic` by accident.
    """
    if path.resolve() != PUBLISHED.resolve():
        return
    if artifact.get("is_real") is True and artifact["data"]["kind"] == PUBLISHABLE_KIND:
        return
    raise DispatchError(
        f"refusing to write {path}: it is defined as real or absent, and this "
        f"run is is_real={artifact.get('is_real')!r} kind={artifact['data']['kind']!r}. "
        "Pass --out to write it somewhere that is not the published path."
    )


def _report(artifact: dict) -> None:
    if artifact["failed_gate"]:
        print(f"REFUSED by {artifact['failed_gate']}: {artifact['failure']}")
        return

    reference = artifact["reference_arm"]
    rows = {a["id"]: a for a in artifact["arms"]}
    print()
    # ASCII only. The console this runs on is cp1252 and a `∩` in a header is
    # enough to end the run with UnicodeEncodeError after every arm has been
    # scored — measured, and this repository has met the same encoding before.
    print(f"{'arm':<26} {'MAE':>12} {'imputed':>8} {'MAE_isec':>12} {'fit_s':>8} {'r vs ref':>9}")
    for arm in artifact["arms"]:
        ratio = arm["mae"] / rows[reference]["mae"] if reference in rows else float("nan")
        print(
            f"{arm['id']:<26} {arm['mae']:>12,.2f} {arm['imputed_folds']:>8} "
            f"{arm['mae_intersection']:>12,.2f} {arm['fit_cpu_s']:>8.2f} {ratio:>9.3f}"
        )
    print(
        f"\nreference: {reference}   verdict base: {len(artifact['folds_verdict_base'])} fold(s)"
        f"   intersection: {len(artifact['folds_intersected'])}"
        f"   rule: {artifact['imputation_rule']}"
    )
    if artifact["candidates_without_ground_truth"]:
        print(
            f"  {len(artifact['candidates_without_ground_truth'])} candidate(s) had no actual "
            "for the naive either and are out of the base entirely"
        )
    for pair, call in artifact["verdict"].items():
        flag = "" if call["bands_agree"] else "   <<< THE BAND MOVES IF THE RULE CHANGES"
        print(
            f"  {pair}: r={call['r']:.3f} ({call['band']}) | "
            f"dropping instead of imputing: r={call['r_if_folds_dropped']:.3f} "
            f"({call['band_if_folds_dropped']}){flag}"
        )
    for pair, report in artifact["uncertainty"].items():
        low, high = report["mae_ratio"]["ci95"]
        print(f"  {pair}: 95% CI [{low:.3f}, {high:.3f}] over origins")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        artifact = run_lane(args)
    except (DispatchError, NoRealDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out: Path = args.out or PUBLISHED
    try:
        refuse_to_publish_a_fixture(out, artifact)
    except DispatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    _report(artifact)
    print(f"\nwrote {out}")
    return 1 if artifact["failed_gate"] else 0


if __name__ == "__main__":
    sys.exit(main())
