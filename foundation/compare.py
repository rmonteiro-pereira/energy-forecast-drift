"""Assembles the lane artifact, and refuses to write one that cannot be trusted.

Order matters here and each step is placed where it is because the alternative
was measured and found green on the defect:

1. **Guard the series once**, before the arms fork. Inside an adapter, the same
   missing hour would reach the foundation model interpolated and the GBM as NaN
   consumed natively — the arms would be scored on different data, which is the
   thing the fold contract exists to forbid.
2. **Score every arm** on the same pinned candidate cutoffs, metering cost on
   three lines that are never summed.
3. **Align**, because pinning candidates does not pin the folds actually used: a
   fold is dropped whole when any horizon is unscorable and that depends on what
   the model returned. The intersection is survivorship filtering, so both ways
   an arm can lose a fold are reported separately rather than netted.
4. **Interval over origins**, not over predictions.
5. **Every gate, then write.** A gate that runs after the file is on disk has
   already lost.

A refusal is not an exception that escapes: `build_artifact` catches the gate
errors it knows and stamps `failed_gate`, so the reason survives into the record
instead of into a traceback nobody keeps.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from features import build as build_mod
from foundation import cost as cost_mod
from foundation import guards
from foundation.uncertainty import UncertaintyError, assert_block_is_origin, paired_block_bootstrap
from models import arms as arms_mod
from models import backtest, train

#: Everything a refusal can be. Mirrors the artifact's `failed_gate` enum.
GATES = (
    "contiguity",
    "foresight",
    "fold-identity",
    "arm-composition",
    "arm-params",
    "arm-cadence",
    "cost-provenance",
    "uncertainty-block",
)


@dataclass
class ArmRun:
    """One scored arm plus everything the artifact has to say about it."""

    arm_id: str
    result: backtest.BacktestResult
    cost: dict
    features: list[str]
    refits: int
    fit_anchor_utc: str | None
    params: dict
    in_domain_training_hours: int
    context_hours: int | None = None
    weights: dict | None = None


def score_arm(
    arm_id: str,
    predict_factory: Callable[[], object],
    series: pd.Series,
    cutoffs: Sequence[pd.Timestamp],
    *,
    horizons: tuple[int, ...] = backtest.DEFAULT_HORIZONS,
    n_threads: int = 1,
) -> tuple[backtest.BacktestResult, cost_mod.CostMeter]:
    """Run one arm, metering the inference line. Fit is metered by the caller."""
    meter = cost_mod.CostMeter()
    predict_fn = predict_factory()
    with meter.timing("infer"):
        result = backtest.run(series, predict_fn, horizons=horizons, cutoffs=cutoffs)
    del n_threads  # recorded in the hardware block, not used here
    return result, meter


def build_artifact(
    runs: dict[str, ArmRun],
    *,
    cutoff_candidates: Sequence[pd.Timestamp],
    contiguity: dict,
    is_real: bool,
    data_kind: str,
    n_threads: int = 1,
    reference_arm: str | None = None,
    warning: str | None = None,
) -> dict:
    """Every gate, then the record. Refusals are stamped, not raised at the caller.

    `data.is_real` mirrors the top-level flag rather than merely existing: the
    pytest half of this repository's honesty check *skips* an artifact whose
    `data` block has no `is_real`, so an artifact of a new shape could slip past
    both halves of the gate that exists to catch exactly that.
    """
    try:
        return _build(
            runs,
            cutoff_candidates=cutoff_candidates,
            contiguity=contiguity,
            is_real=is_real,
            data_kind=data_kind,
            n_threads=n_threads,
            reference_arm=reference_arm,
            warning=warning,
        )
    except (guards.LaneGateError, arms_mod.ArmGateError, cost_mod.CostGateError) as exc:
        return _refusal(exc.gate, str(exc), is_real, data_kind, warning)
    except train.FoldIdentityError as exc:
        return _refusal("fold-identity", str(exc), is_real, data_kind, warning)
    except UncertaintyError as exc:
        return _refusal(exc.gate, str(exc), is_real, data_kind, warning)


def _refusal(gate: str, message: str, is_real: bool, data_kind: str, warning: str | None) -> dict:
    if gate not in GATES:  # pragma: no cover - guard against a typo becoming a field value
        raise ValueError(f"{gate!r} is not one of the declared gates")
    return {
        "is_real": is_real,
        "warning": warning,
        "data": {"kind": data_kind, "is_real": is_real},
        "failed_gate": gate,
        "failure": message,
        "arms": [],
    }


def _build(
    runs: dict[str, ArmRun],
    *,
    cutoff_candidates: Sequence[pd.Timestamp],
    contiguity: dict,
    is_real: bool,
    data_kind: str,
    n_threads: int,
    reference_arm: str | None,
    warning: str | None,
) -> dict:
    if not runs:
        raise guards.LaneGateError("fold-identity", "no arms: the artifact would be vacuous")

    aligned, fold_record = train.align_arms({k: r.result for k, r in runs.items()})

    for arm_id, run in runs.items():
        if arm_id in arms_mod.ARMS:
            spec = arms_mod.ARMS[arm_id]
            if set(run.features) != set(spec.expected_informative):
                raise arms_mod.ArmGateError(
                    "arm-composition",
                    f"{arm_id}: {len(run.features)} features, expected "
                    f"{len(spec.expected_informative)}",
                )
            arms_mod.assert_cadence(arm_id, run.refits, run.fit_anchor_utc, cutoff_candidates[0])

    gbm_params = [r.params for k, r in runs.items() if k.startswith("lgbm_")]
    if gbm_params and any(p != gbm_params[0] for p in gbm_params[1:]):
        raise arms_mod.ArmGateError(
            "arm-params", "the lgbm_* arms were not fitted with identical hyperparameters"
        )

    reference = reference_arm or "lgbm_17_demand_only"
    uncertainty = {}
    if reference in aligned:
        for arm_id, result in aligned.items():
            if arm_id == reference:
                continue
            report = paired_block_bootstrap(result.predictions, aligned[reference].predictions)
            assert_block_is_origin(report, len(fold_record["folds_intersected"]))
            uncertainty[f"{arm_id}/{reference}"] = report

    artifact = {
        "is_real": is_real,
        "warning": warning,
        "data": {"kind": data_kind, "is_real": is_real},
        "failed_gate": None,
        "cutoff_candidates": [pd.Timestamp(c).isoformat() for c in cutoff_candidates],
        "folds_intersected": fold_record["folds_intersected"],
        "contiguity": contiguity,
        "reference_arm": reference,
        "hardware": cost_mod.hardware_block(n_threads=n_threads),
        "arms": [
            {
                "id": arm_id,
                "name": arm_id.split("@")[0],
                "n": aligned[arm_id].overall["n"],
                "mae": round(aligned[arm_id].overall["mae"], 4),
                "mape_pct": round(aligned[arm_id].overall["mape_pct"], 4),
                "rmse": round(aligned[arm_id].overall["rmse"], 4),
                "bias": round(aligned[arm_id].overall["bias"], 4),
                "features": run.features,
                "features_informative": len(run.features),
                "refits": run.refits,
                "fit_anchor_utc": run.fit_anchor_utc,
                "params": run.params,
                "context_hours": run.context_hours,
                "feature_reach_hours": build_mod.MIN_HISTORY_HOURS - 1,
                "in_domain_training_hours": run.in_domain_training_hours,
                "unscorable_by_own_failure": fold_record["arms"][arm_id][
                    "unscorable_by_own_failure"
                ],
                "folds_dropped_vs_intersection": fold_record["arms"][arm_id][
                    "folds_dropped_vs_intersection"
                ],
                "weights": run.weights,
                **run.cost,
            }
            for arm_id, run in runs.items()
        ],
        "uncertainty": uncertainty,
    }

    cost_mod.assert_cost_provenance(artifact)
    return artifact
