"""Paired bootstrap over origins, because the 1,320 predictions are not 1,320 facts.

This repository has no uncertainty machinery at all around the model comparison
— `grep -rn "diebold\\|block_bootstrap\\|confidence_interval\\|paired.*bootstrap"
models/ --include=*.py` returns nothing — and it publishes `-77.17%` and `24/24`
as if they were exact. For a delta that large the point estimate is harmless
folklore. For the single-digit delta this lane expects between a foundation model
and a demand-only GBM, it is the whole answer, and a number without an interval
would be the most quotable thing in the artifact and the least defensible.

**The block is the origin, and that is the entire design.** Each fold produces 24
predictions from one forecast origin: same model state, same recent history, same
weather regime, one shared day-ahead error. Resampling the 1,320 rows
independently pretends those 24 are 24 independent observations, which understates
the interval — measured here at roughly a fifth of the honest width. Resampling
the 55 origins keeps each fold whole.

**Paired, not two separate intervals.** The arms are scored on the same folds, so
the quantity with an interval is the *difference*, resampled jointly. Two
independent CIs that happen to overlap say nothing about whether one arm beat the
other on the days they both saw.

The result is a field in the artifact and is **forbidden as a headline** — G10 is
declared non-blocking for CI precisely so that it blocks the review instead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: The column that identifies a forecast origin in `BacktestResult.predictions`.
BLOCK_KEY = "cutoff_utc"
DEFAULT_RESAMPLES = 2000
#: Fixed so the interval is reproducible; recorded in the artifact so a reader
#: can regenerate it rather than trust it.
DEFAULT_SEED = 20260806


class UncertaintyError(RuntimeError):
    """The interval was computed in a way that misstates it."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(message)
        self.gate = gate


def _aligned_errors(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """One row per (origin, horizon), carrying both arms' absolute errors."""
    keys = [BLOCK_KEY, "horizon_h"]
    merged = a[[*keys, "abs_error"]].merge(
        b[[*keys, "abs_error"]], on=keys, suffixes=("_a", "_b"), how="inner"
    )
    if len(merged) != len(a) or len(merged) != len(b):
        raise UncertaintyError(
            "fold-identity",
            f"the arms do not share their rows ({len(a)} and {len(b)} scored, "
            f"{len(merged)} in common); align them before asking for an interval",
        )
    return merged


def paired_block_bootstrap(
    predictions_a: pd.DataFrame,
    predictions_b: pd.DataFrame,
    *,
    n_resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
    by_point: bool = False,
) -> dict:
    """95% CI for `mae(a) - mae(b)` and `mae(a) / mae(b)`, resampling whole origins.

    `by_point=True` resamples the 1,320 rows independently instead. It exists so
    the understatement can be *measured* rather than asserted, and so a test can
    show the two disagree; it must never reach the artifact, which is what G10
    checks.
    """
    errors = _aligned_errors(predictions_a, predictions_b)
    rng = np.random.default_rng(seed)

    if by_point:
        units = [np.array([i]) for i in range(len(errors))]
    else:
        units = [np.asarray(rows) for rows in errors.groupby(BLOCK_KEY).indices.values()]

    ea = errors["abs_error_a"].to_numpy()
    eb = errors["abs_error_b"].to_numpy()
    deltas = np.empty(n_resamples)
    ratios = np.empty(n_resamples)

    for i in range(n_resamples):
        picked = rng.integers(0, len(units), len(units))
        rows = np.concatenate([units[j] for j in picked])
        mae_a = ea[rows].mean()
        mae_b = eb[rows].mean()
        deltas[i] = mae_a - mae_b
        ratios[i] = mae_a / mae_b

    return {
        "block": "point" if by_point else BLOCK_KEY,
        "n_blocks": len(units),
        "n_predictions": len(errors),
        "n_resamples": n_resamples,
        "seed": seed,
        "mae_delta": {
            "point": float(ea.mean() - eb.mean()),
            "ci95": [float(np.quantile(deltas, 0.025)), float(np.quantile(deltas, 0.975))],
        },
        "mae_ratio": {
            "point": float(ea.mean() / eb.mean()),
            "ci95": [float(np.quantile(ratios, 0.025)), float(np.quantile(ratios, 0.975))],
        },
    }


def assert_block_is_origin(report: dict, expected_blocks: int) -> None:
    """G10 — the interval must come from origins, not from points.

    Non-blocking for CI by declaration, and this is what makes that honest: the
    check exists and refuses, it simply refuses at review time rather than in the
    `test` job. A report that resampled points is not a weaker interval, it is a
    different and wrong one.
    """
    if report.get("block") != BLOCK_KEY:
        raise UncertaintyError(
            "uncertainty-block",
            f"the interval resampled {report.get('block')!r}; the 24 horizons of one "
            "origin share a model state and a weather regime and are not independent",
        )
    if report.get("n_blocks") != expected_blocks:
        raise UncertaintyError(
            "uncertainty-block",
            f"resampled {report.get('n_blocks')} block(s) against {expected_blocks} fold(s)",
        )


def reopen_timesfm(ratio_ci: list[float], band: tuple[float, float] = (0.95, 1.10)) -> bool:
    """Whether the TimesFM cut reopens: does the **interval** intersect the band?

    Not the point estimate. The RFC's first version triggered on
    `mae(chronos)/mae(lgbm) in [0.95, 1.10]` — a decision taken on a point value
    of exactly the kind this module exists because the repository publishes
    without an interval. Measured on 55 origins, the interval's width is of the
    same order as the band's, so a point trigger is a coin flip dressed as a rule.

    The band itself is an *operational tie* that was chosen, not measured, and
    saying so is part of the contract.
    """
    low, high = sorted(ratio_ci)
    return not (high < band[0] or low > band[1])
