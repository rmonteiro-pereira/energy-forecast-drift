"""Global LightGBM forecaster, plugged into the existing walk-forward protocol.

Shape of the model
------------------
One **global, direct** model: a single booster predicts every horizon, with
`horizon_h` as an input feature, instead of 24 separate models or a recursive
one-step model fed its own output. Direct multi-horizon is the right default
here — it cannot compound its own error the way recursion does, and a global
model sees 24x more rows than a per-horizon fit, which matters a lot when the
history is a few months rather than a few years.

Refit cadence
-------------
The model is **retrained at every fold cutoff** on everything whose target hour
had already happened at that instant. That is the expensive but honest choice:
fold 56's model never saw a row fold 1's model could not have seen, so the
comparison against the seasonal-naive baseline is on identical information.

This module deliberately exposes the same `predict_fn(history, targets, cutoff)`
callable that `models.backtest.run` already drives for the baseline. The
evaluation protocol is untouched — only the model behind it changes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

from features import build as build_mod
from models.baseline import TemporalLeakageError

log = logging.getLogger(__name__)

NAME = "lightgbm_global_direct"
SEED = 20260728

DEFAULT_PARAMS: dict = {
    # L1 because MAE is the number this project is judged on; optimising L2 and
    # reporting L1 is a small, common, avoidable mismatch.
    "objective": "l1",
    "metric": "l1",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 40,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "num_threads": 0,
    "verbose": -1,
    "seed": SEED,
    # Reproducibility is a testable property here (the poisoned-future test
    # compares metrics for equality), so determinism is switched on explicitly.
    "deterministic": True,
    "force_row_wise": True,
}
DEFAULT_NUM_BOOST_ROUND = 300


def train_booster(
    design: pd.DataFrame,
    params: dict | None = None,
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
) -> lgb.Booster:
    """Fit a booster on the labelled rows of a design matrix."""
    labelled = design[design[build_mod.TARGET_COLUMN].notna()]
    if labelled.empty:
        raise ValueError("No labelled rows to train on.")

    dataset = lgb.Dataset(
        build_mod.feature_frame(labelled),
        label=labelled[build_mod.TARGET_COLUMN].to_numpy(dtype="float64"),
        categorical_feature=list(build_mod.CATEGORICAL_FEATURES),
        free_raw_data=True,
    )
    return lgb.train({**DEFAULT_PARAMS, **(params or {})}, dataset, num_boost_round=num_boost_round)


@dataclass
class WalkForwardLightGBM:
    """A `predict_fn` for `models.backtest.run` that refits at every cutoff.

    Parameters
    ----------
    panel:
        The full gapless hourly panel. The object holds the whole series, but a
        row can only ever enter training once its *target* hour is strictly
        before the fold cutoff — enforced below and asserted by the tests.
    """

    panel: pd.DataFrame
    horizons: tuple[int, ...] = tuple(range(1, 25))
    params: dict = field(default_factory=dict)
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND
    train_stride_hours: int = 6
    #: Features blanked in *both* the training and the prediction design. One
    #: value, used in both places, because applying an ablation to only one of
    #: them asks the model at inference for information it never fitted on.
    drop_features: tuple[str, ...] = ()
    #: When set, fit **once** on the rows observable at this instant and reuse
    #: that booster for every fold — the refit cadence of a zero-shot model,
    #: which refits never. It is pinned rather than inferred because the anchor
    #: is otherwise a free parameter sitting under the comparison: moving it
    #: moves this arm's MAE by roughly 3x.
    freeze_at: pd.Timestamp | None = None

    train_design: pd.DataFrame = field(init=False, repr=False)
    fits: int = field(init=False, default=0)
    last_booster: lgb.Booster | None = field(init=False, default=None, repr=False)
    last_train_rows: int = field(init=False, default=0)
    #: CPU-seconds spent inside `train_booster`, accumulated across refits.
    #:
    #: Metered here because there is nowhere else it can be. The refit happens
    #: *inside* the `__call__` that the harness meters as inference, so a caller
    #: wrapping `backtest.run` can only ever produce one number for both. The
    #: lane's cost contract keeps `fit` and `infer` on separate lines precisely
    #: because the refit is 98.7% of this model's cost and a zero-shot model
    #: refits never — collapsing them hands the foundation model a ~76x win that
    #: belongs to the protocol. The first lane artifact declared `refits: 13`
    #: next to `fit_cpu_s: 0.0` for exactly this reason.
    fit_cpu_s: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        origins = build_mod.training_origins(
            self.panel.index,
            stride_hours=self.train_stride_hours,
            max_horizon=max(self.horizons),
        )
        self.train_design = build_mod.build_design_matrix(
            self.panel, origins, self.horizons, drop_features=self.drop_features
        )
        log.info(
            "LightGBM design matrix: %d row(s) from %d origin(s), %d feature(s)",
            len(self.train_design),
            len(origins),
            len(build_mod.FEATURE_COLUMNS),
        )

    # -- the backtest calls this ------------------------------------------
    def __call__(
        self,
        history: pd.Series,
        target_times: pd.DatetimeIndex,
        cutoff: pd.Timestamp,
    ) -> pd.Series:
        if len(history.index) and history.index.max() >= cutoff:
            raise TemporalLeakageError(
                f"history ends at {history.index.max()}, which is not strictly "
                f"before the fold cutoff {cutoff}"
            )

        # A frozen arm fits once, at the pinned anchor, and reuses that booster.
        # `self.freeze_at` rather than "the first cutoff we happen to see"
        # because the caller knows the candidate list and this object does not.
        fit_at = self.freeze_at if self.freeze_at is not None else cutoff
        if self.last_booster is not None and self.freeze_at is not None:
            booster = self.last_booster
        else:
            train = self.training_slice(fit_at)
            if train.empty:
                raise ValueError(f"No training rows available before {fit_at}.")
            started = time.process_time()
            booster = train_booster(train, self.params, self.num_boost_round)
            self.fit_cpu_s += time.process_time() - started
            self.fits += 1
            self.last_booster = booster
            self.last_train_rows = len(train)

        design = build_mod.build_design_matrix(
            self.panel,
            pd.DatetimeIndex([cutoff]),
            self.horizons,
            drop_features=self.drop_features,
        )
        design = design[design["target_utc"].isin(target_times)]
        preds = booster.predict(build_mod.feature_frame(design))
        return pd.Series(
            np.asarray(preds, dtype="float64"),
            index=pd.DatetimeIndex(design["target_utc"]),
            name="prediction",
        ).reindex(target_times)

    def training_slice(self, cutoff: pd.Timestamp) -> pd.DataFrame:
        """Rows whose label was already observable at `cutoff` — nothing else.

        `target_utc < cutoff` is the single condition that matters: the label is
        the demand *at* the target hour, so a row is usable exactly when that
        hour has completed. The features were already pinned to their own
        (earlier) origin by the design matrix.
        """
        train = self.train_design[self.train_design["target_utc"] < cutoff]
        train = train[train[build_mod.TARGET_COLUMN].notna()]
        if len(train) and train["target_utc"].max() >= cutoff:  # pragma: no cover - guard
            raise TemporalLeakageError(
                f"training slice reaches {train['target_utc'].max()}, at or after {cutoff}"
            )
        return train


def fit_final(
    panel: pd.DataFrame,
    horizons: tuple[int, ...] = tuple(range(1, 25)),
    params: dict | None = None,
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
    train_stride_hours: int = 6,
) -> tuple[lgb.Booster, pd.DataFrame]:
    """Refit on the whole panel — the artifact that goes to the registry."""
    origins = build_mod.training_origins(
        panel.index, stride_hours=train_stride_hours, max_horizon=max(horizons)
    )
    design = build_mod.build_design_matrix(panel, origins, horizons)
    return train_booster(design, params, num_boost_round), design


def importance(booster: lgb.Booster, top: int = 12) -> list[dict]:
    """Gain-based feature importance, biggest first — for the metrics artifact."""
    gains = booster.feature_importance(importance_type="gain")
    names = booster.feature_name()
    total = float(gains.sum()) or 1.0
    ranked = sorted(zip(names, gains, strict=True), key=lambda kv: kv[1], reverse=True)
    return [
        {"feature": name, "gain_pct": round(100.0 * float(gain) / total, 2)}
        for name, gain in ranked[:top]
    ]
