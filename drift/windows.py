"""Cut the history into train / reference / current, and score the last two.

Why three windows and not two
-----------------------------
Drift monitoring compares a **reference** window ("what normal looked like")
against a **current** window ("what is happening now"). The trap is scoring the
reference window with a model that was fitted on it: the reference errors come
out flatteringly small, every later window looks degraded, and the performance
detector fires forever.

So the panel is cut three ways along the time axis:

    |-------------- train --------------|--- reference ---|--- current ---|
                                         ^                 ^              ^
                                         |                 |              now
                                         |                 current_start
                                         reference_start

the booster is fitted on `train` **only**, and both later windows are scored by
that frozen model. Both are out of sample, so their errors are comparable — which
is exactly the situation in production, where a deployed model is frozen and the
world moves underneath it.

Feature, target and prediction drift then read the same two frames: the design
matrix columns, the label `y`, and the frozen model's `prediction`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import lightgbm as lgb
import pandas as pd

from drift.config import DEFAULT_CURRENT_DAYS, DEFAULT_REFERENCE_DAYS
from features import build as build_mod
from models import lgbm as lgbm_mod

log = logging.getLogger(__name__)

PREDICTION_COLUMN = "prediction"
ERROR_COLUMN = "error"
ABS_ERROR_COLUMN = "abs_error"
ABS_PCT_ERROR_COLUMN = "abs_pct_error"


class NotEnoughHistoryError(ValueError):
    """The panel cannot be split into three non-empty windows."""


@dataclass
class ScoredWindows:
    """Reference and current design matrices, scored by one frozen booster."""

    reference: pd.DataFrame
    current: pd.DataFrame
    booster: lgb.Booster = field(repr=False)
    split: dict = field(default_factory=dict)
    train_rows: int = 0

    @property
    def feature_columns(self) -> tuple[str, ...]:
        return build_mod.FEATURE_COLUMNS


def _add_errors(frame: pd.DataFrame) -> pd.DataFrame:
    """Signed / absolute / percentage error columns for the performance detector."""
    out = frame.copy()
    out[ERROR_COLUMN] = out[PREDICTION_COLUMN] - out[build_mod.TARGET_COLUMN]
    out[ABS_ERROR_COLUMN] = out[ERROR_COLUMN].abs()
    actual = out[build_mod.TARGET_COLUMN].abs()
    # MAPE is undefined at zero demand; such an hour is a data error anyway.
    out[ABS_PCT_ERROR_COLUMN] = (out[ABS_ERROR_COLUMN] / actual.where(actual > 0)) * 100.0
    return out


def build_windows(
    panel: pd.DataFrame,
    *,
    reference_days: int = DEFAULT_REFERENCE_DAYS,
    current_days: int = DEFAULT_CURRENT_DAYS,
    horizons: tuple[int, ...] = tuple(range(1, 25)),
    stride_hours: int = 6,
    num_boost_round: int = lgbm_mod.DEFAULT_NUM_BOOST_ROUND,
    booster: lgb.Booster | None = None,
) -> ScoredWindows:
    """Split `panel`, fit on the oldest slice, score the two newest ones.

    `booster` may be supplied to score against an already-trained model (that is
    what the daily pipeline does with the registry champion); when it is `None`
    a booster is fitted here on the train window alone.
    """
    if panel.empty:
        raise NotEnoughHistoryError("The panel is empty.")

    end = panel.index.max()
    current_start = end - pd.Timedelta(days=current_days)
    reference_start = current_start - pd.Timedelta(days=reference_days)

    origins = build_mod.training_origins(
        panel.index, stride_hours=stride_hours, max_horizon=max(horizons)
    )
    design = build_mod.build_design_matrix(panel, origins, horizons)
    design = design[design[build_mod.TARGET_COLUMN].notna()]
    if design.empty:
        raise NotEnoughHistoryError(
            "No labelled design rows — the panel is shorter than the feature warm-up "
            f"({build_mod.MIN_HISTORY_HOURS}h) plus one horizon."
        )

    target = design["target_utc"]
    train = design[target < reference_start]
    reference = design[(target >= reference_start) & (target < current_start)]
    current = design[target >= current_start]

    empty = [
        name
        for name, frame in (("train", train), ("reference", reference), ("current", current))
        if frame.empty
    ]
    if empty:
        raise NotEnoughHistoryError(
            f"Window(s) {', '.join(empty)} are empty: the panel spans "
            f"{panel.index.min().date()} to {end.date()}, which is not enough for a "
            f"{reference_days}-day reference plus a {current_days}-day current window "
            f"on top of the {build_mod.MIN_HISTORY_HOURS}h feature warm-up."
        )

    booster_source = "supplied"
    if booster is None:
        booster = lgbm_mod.train_booster(train, num_boost_round=num_boost_round)
        booster_source = "fitted_on_train_window"
        log.info("Fitted the drift reference booster on %d train row(s).", len(train))

    scored = {}
    for name, frame in (("reference", reference), ("current", current)):
        predicted = frame.copy()
        predicted[PREDICTION_COLUMN] = booster.predict(build_mod.feature_frame(frame))
        scored[name] = _add_errors(predicted)

    split = {
        "strategy": (
            "time-ordered train / reference / current; the booster is fitted on the "
            "train window only, so both scored windows are out of sample"
        ),
        "panel_start_utc": panel.index.min().isoformat(),
        "panel_end_utc": end.isoformat(),
        "reference_start_utc": reference_start.isoformat(),
        "current_start_utc": current_start.isoformat(),
        "reference_days": reference_days,
        "current_days": current_days,
        "horizons_h": [int(h) for h in horizons],
        "origin_stride_hours": stride_hours,
        "rows": {
            "train": len(train),
            "reference": len(reference),
            "current": len(current),
        },
        "booster_source": booster_source,
    }

    return ScoredWindows(
        reference=scored["reference"],
        current=scored["current"],
        booster=booster,
        split=split,
        train_rows=len(train),
    )
