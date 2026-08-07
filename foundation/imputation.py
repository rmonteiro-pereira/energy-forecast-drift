"""Clause 1b — the verdict is not allowed to come out of the intersection.

`models.train.align_arms` puts every arm on the folds they all scored, which is
what makes `n` identical and the comparison controlled. It is also **survivorship
filtering**, and its own docstring says so: an arm that fails precisely on the
hardest days is then scored on the easier remainder.

Until this module existed the lane reported that filtering and then published the
filtered number anyway. It was invisible because every arm scored every fold on
the fixture, so the intersection *was* the candidate list and the two answers
agreed. The moment a TSFM fails a horizon — the single case Clause 1b was written
for — the intersection drops that fold and every surviving arm is compared on the
subset where the weak arm happened to succeed. **An arm gets flattered by its own
failures**, and the gate reports green while the estimand changes underneath it.

So the verdict is evaluated over the full candidate list, with each arm's
unscorable folds scored by a declared pessimistic rule: **the `seasonal_naive`
error on that fold**. Substituting the naive's rows rather than a fabricated
number is what makes it a *rule* — the arm is credited with exactly the error the
trivial model would have made, and nothing about the fold is invented.

Two honesty notes that belong next to the code, not in a footnote:

* **The rule is a choice, not a measurement** (§6, risk 7). Charging the naive's
  error is conservative and arbitrary; a reviewer may prefer another rule. That
  is why `sensitivity` recomputes the verdict under "drop the fold" instead and
  records whether the band moves. D10's reversal criterion *is* that comparison,
  and without it the decision would carry a criterion nothing evaluates.
* **A candidate the naive itself cannot score is not imputed, it is excluded.**
  There is no ground truth on that fold for anyone, so charging an arm the error
  of a model that also failed would be inventing the comparison rather than
  making it pessimistic. Those folds are recorded separately.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from models import backtest

#: Named in the artifact so the number can never be read without the rule that
#: produced it. Changing the rule changes this string, which changes the diff.
IMPUTATION_RULE = "seasonal_naive_error_on_unscorable_fold"

#: The arm whose per-fold error fills an unscorable fold. It is the trivial
#: model this whole repository exists to beat, which is what makes charging it
#: to a failing arm pessimistic rather than generous.
FILLER_ARM = "seasonal_naive"

#: Clause 5's two boundaries. They are **not** symmetric and the asymmetry is the
#: whole content of the table: `r < 1.00` beats, `1.00 <= r <= 1.25` is
#: competitive, `r > 1.25` is not. Writing this as one loop with `<=` puts an
#: exact tie — the single most likely value to argue about — in the wrong band.
BEATS_BELOW = 1.00
COMPETITIVE_THROUGH = 1.25


class ImputationError(RuntimeError):
    """Clause 1b cannot be honoured. `gate` is what goes into `failed_gate`."""

    gate = "imputation"

    def __init__(self, message: str) -> None:
        super().__init__(message)


def band(ratio: float) -> str:
    """The published verdict for a ratio. Both boundaries are pinned by test."""
    if ratio < BEATS_BELOW:
        return "beats"
    if ratio <= COMPETITIVE_THROUGH:
        return "competitive"
    return "not competitive"


def verdict_base(
    filler: backtest.BacktestResult, candidates: Sequence[pd.Timestamp]
) -> tuple[pd.DatetimeIndex, list[str]]:
    """The folds the verdict runs over, and the candidates that fell out of it.

    "The full `cutoff_candidates`" has one honest exception: a candidate the
    seasonal naive could not score has no actual to compare anything against.
    Excluding it is not survivorship filtering — nothing survived there.
    """
    wanted = pd.DatetimeIndex(sorted(set(list(candidates))))
    if len(wanted) == 0:
        raise ImputationError("no cutoff candidates: the verdict would have no base")

    scored = pd.DatetimeIndex(sorted(set(filler.folds)))
    base = wanted.intersection(scored)
    if len(base) == 0:
        raise ImputationError(
            f"{FILLER_ARM} scored none of the {len(wanted)} candidate(s); there is "
            "no ground truth to impute against"
        )
    return base, sorted(t.isoformat() for t in wanted.difference(scored))


def impute(
    arm: backtest.BacktestResult,
    filler: backtest.BacktestResult,
    base: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, list[str]]:
    """The arm's predictions over `base`, with its unscorable folds charged.

    Returns the frame and the folds that were filled. The filler's rows are
    substituted whole — prediction *and* actual — so the arm's error on that fold
    is exactly the naive's error and no value is synthesised.
    """
    own = arm.predictions[arm.predictions["cutoff_utc"].isin(base)]
    missing = base.difference(pd.DatetimeIndex(sorted(set(own["cutoff_utc"]))))
    if len(missing) == 0:
        return own.sort_values(["cutoff_utc", "horizon_h"]).reset_index(drop=True), []

    filled = filler.predictions[filler.predictions["cutoff_utc"].isin(missing)]
    if len(filled) == 0:  # pragma: no cover - verdict_base makes this unreachable
        raise ImputationError(
            f"{len(missing)} fold(s) need imputing and {FILLER_ARM} scored none of them"
        )
    frame = pd.concat([own, filled], ignore_index=True)
    return (
        frame.sort_values(["cutoff_utc", "horizon_h"]).reset_index(drop=True),
        sorted(t.isoformat() for t in missing),
    )


def summarise(frame: pd.DataFrame) -> dict:
    """Metrics for an imputed frame, through the harness's own summariser.

    `backtest._summarise` is private and called anyway, deliberately: it was
    factored out so `run` and `rescore` could not drift apart, and a third
    implementation of the same metrics is precisely the drift it exists to
    prevent. Reaching for it is the smaller sin.
    """
    _by_horizon, overall = backtest._summarise(frame)
    return overall


def sensitivity(imputed: dict[str, float], intersected: dict[str, float], reference: str) -> dict:
    """D10's reversal criterion, evaluated rather than described.

    The decision says: if an arm has imputed folds and the Clause 5 band moves
    when the rule is swapped for "drop the fold", the decision is wrong and the
    verdict does not ship. `bands_agree` is that comparison; a consumer that
    publishes a verdict while it is `false` is publishing a number that depends
    on an arbitrary choice.
    """
    out = {}
    for arm_id, mae in imputed.items():
        if arm_id == reference:
            continue
        ratio = mae / imputed[reference]
        ratio_dropped = intersected[arm_id] / intersected[reference]
        out[f"{arm_id}/{reference}"] = {
            "rule": IMPUTATION_RULE,
            "r": round(ratio, 6),
            "band": band(ratio),
            "r_if_folds_dropped": round(ratio_dropped, 6),
            "band_if_folds_dropped": band(ratio_dropped),
            "bands_agree": band(ratio) == band(ratio_dropped),
        }
    return out
