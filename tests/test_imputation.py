"""Clause 1b — and the arm that gets flattered by its own failures.

Every test that matters here has to **manufacture a failure**, because on the
fixture every arm scores every fold: `imputed_folds` is 0 everywhere, the verdict
base equals the intersection, and the two answers agree. That is exactly the
condition under which this code looks correct while doing nothing, and it is why
the defect survived three adversarial rounds and a full implementation pass — the
clause was written for the one case the fixture never produces.

So the arm below fails **on purpose, on the folds where it would have scored
worst**. That is not a contrived case; it is the case Clause 1b names. A
foundation model that returns NaN does so on the hours it finds hardest, and an
intersection then scores every surviving arm on the days the weak one happened
to survive.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from foundation import compare, cost, imputation
from models import arms as arms_mod
from models import backtest, baseline

HOUR = pd.Timedelta(hours=1)


@pytest.fixture(scope="module")
def series() -> pd.Series:
    index = pd.date_range("2026-01-01", periods=24 * 40, freq="h", name="timestamp_utc")
    hours = np.arange(len(index))
    values = (
        10_000
        + 2_000 * np.sin(hours * 2 * np.pi / 24)
        + 800 * np.sin(hours * 2 * np.pi / 168)
        # A hard stretch in the middle: the naive is worst here, so this is
        # where a failing arm has the most to gain by not being scored.
        + np.where((hours > 24 * 20) & (hours < 24 * 26), 4_000.0, 0.0)
    )
    return pd.Series(values, index=index, name="demand_mwh")


@pytest.fixture(scope="module")
def cutoffs(series: pd.Series) -> list[pd.Timestamp]:
    return backtest.make_cutoffs(pd.DatetimeIndex(series.index), 3, (1, 2, 3), 12, 168)


@pytest.fixture(scope="module")
def naive(series: pd.Series, cutoffs) -> backtest.BacktestResult:
    return backtest.run(series, baseline.predict, horizons=(1, 2, 3), cutoffs=cutoffs)


def _arm(series: pd.Series, *, bias: float, fails_on: set[pd.Timestamp] = frozenset()):
    """A predictor with a fixed bias that returns NaN on the folds named."""

    def predict(history, target_times, cutoff):
        if cutoff in fails_on:
            return pd.Series(np.nan, index=target_times, name="prediction")
        return pd.Series(
            series.reindex(target_times).to_numpy() + bias, index=target_times, name="prediction"
        )

    return predict


# --------------------------------------------------------------------------
# Clause 5's boundaries. An exact tie is the value people argue about.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (0.5, "beats"),
        (0.999999, "beats"),
        (1.00, "competitive"),
        (1.10, "competitive"),
        (1.25, "competitive"),
        (1.250001, "not competitive"),
        (2.0, "not competitive"),
    ],
)
def test_the_verdict_bands_are_the_table_in_clause_5(ratio, expected):
    """`< 1.00` beats, `1.00 - 1.25` competitive, `> 1.25` not.

    The boundaries are asymmetric and the first draft of `band()` collapsed them
    into one `<=` loop, which put an exact 1.00 in "beats" — the boundary most
    likely to decide a published verdict, in the wrong direction.
    """
    assert imputation.band(ratio) == expected


# --------------------------------------------------------------------------
# The base, and the folds nobody can score.
# --------------------------------------------------------------------------


def test_the_base_is_the_full_candidate_list_when_the_naive_scored_it_all(naive, cutoffs):
    base, missing = imputation.verdict_base(naive, cutoffs)

    assert list(base) == list(cutoffs)
    assert missing == []


def test_a_candidate_the_naive_could_not_score_leaves_the_base_and_is_recorded(naive, cutoffs):
    """Not survivorship filtering: nothing survived there.

    Charging an arm the error of a model that also failed would be inventing the
    comparison rather than making it pessimistic, so the fold is excluded and
    said out loud instead.
    """
    ghost = cutoffs[-1] + pd.Timedelta(days=1)

    base, missing = imputation.verdict_base(naive, [*cutoffs, ghost])

    assert ghost not in base
    assert missing == [ghost.isoformat()]


def test_no_base_at_all_is_a_refusal(naive):
    with pytest.raises(imputation.ImputationError, match="no cutoff candidates"):
        imputation.verdict_base(naive, [])


def test_a_naive_that_scored_nothing_in_the_window_is_a_refusal(naive, cutoffs):
    with pytest.raises(imputation.ImputationError, match="no ground truth"):
        imputation.verdict_base(naive, [cutoffs[-1] + pd.Timedelta(days=5)])


# --------------------------------------------------------------------------
# The imputation itself.
# --------------------------------------------------------------------------


def test_an_arm_that_scored_everything_is_returned_untouched(series, naive, cutoffs):
    honest = backtest.run(series, _arm(series, bias=500.0), horizons=(1, 2, 3), cutoffs=cutoffs)
    base, _ = imputation.verdict_base(naive, cutoffs)

    frame, filled = imputation.impute(honest, naive, base)

    assert filled == []
    assert len(frame) == len(base) * 3


def test_a_failed_fold_is_charged_the_naive_error_on_that_exact_fold(series, naive, cutoffs):
    """Substituted whole — prediction and actual — so nothing is synthesised."""
    failed = {cutoffs[2]}
    arm = backtest.run(
        series, _arm(series, bias=500.0, fails_on=failed), horizons=(1, 2, 3), cutoffs=cutoffs
    )
    base, _ = imputation.verdict_base(naive, cutoffs)

    frame, filled = imputation.impute(arm, naive, base)

    assert filled == [cutoffs[2].isoformat()]
    assert len(frame) == len(base) * 3, "the imputed frame is short a fold"

    charged = frame[frame["cutoff_utc"] == cutoffs[2]]["abs_error"].to_numpy()
    naive_rows = naive.predictions
    expected = naive_rows[naive_rows["cutoff_utc"] == cutoffs[2]]["abs_error"].to_numpy()
    assert np.allclose(charged, expected), "the fold was not charged the naive's own error"


# --------------------------------------------------------------------------
# The defect this module exists for.
# --------------------------------------------------------------------------


def test_the_intersection_flatters_an_arm_that_fails_on_its_worst_folds(series, naive, cutoffs):
    """The measurement that makes Clause 1b not a matter of taste.

    The arm is perfect where it answers and silent on the hard stretch. Under the
    intersection it wins outright, because the intersection also removes those
    folds from the arm it is being compared against. Under Clause 1b it is
    charged the trivial model's error there and the flattery goes away.
    """
    hard = {c for c in cutoffs if pd.Timestamp("2026-01-21") <= c <= pd.Timestamp("2026-01-27")}
    assert len(hard) >= 3, "the fixture window no longer contains the hard stretch"

    quitter = backtest.run(
        series, _arm(series, bias=0.0, fails_on=hard), horizons=(1, 2, 3), cutoffs=cutoffs
    )
    steady = backtest.run(series, _arm(series, bias=900.0), horizons=(1, 2, 3), cutoffs=cutoffs)
    base, _ = imputation.verdict_base(naive, cutoffs)

    quitter_frame, filled = imputation.impute(quitter, naive, base)
    steady_frame, _ = imputation.impute(steady, naive, base)
    r_imputed = (
        imputation.summarise(quitter_frame)["mae"] / imputation.summarise(steady_frame)["mae"]
    )

    intersection = sorted(set(quitter.folds) & set(steady.folds))
    r_intersection = (
        backtest.rescore(quitter, intersection).overall["mae"]
        / backtest.rescore(steady, intersection).overall["mae"]
    )

    assert len(filled) == len(hard)
    assert r_intersection < r_imputed, (
        f"the intersection did not flatter the quitter (r_isec={r_intersection:.3f}, "
        f"r_imputed={r_imputed:.3f}) — this fixture no longer demonstrates the defect"
    )
    assert imputation.band(r_intersection) != imputation.band(r_imputed), (
        "the two rules land in the same band here, so this test would pass "
        "against the intersection-only code it exists to reject"
    )


def test_the_artifact_records_that_the_band_depends_on_the_rule(series, naive, cutoffs):
    """D10's reversal criterion, as a field rather than as a sentence.

    "If the verdict changes band when the imputation rule is swapped for 'drop
    the fold', the decision is wrong and the verdict does not ship" is only a
    criterion if something computes it.
    """
    hard = {c for c in cutoffs if pd.Timestamp("2026-01-21") <= c <= pd.Timestamp("2026-01-27")}
    runs = {
        imputation.FILLER_ARM: _run(imputation.FILLER_ARM, naive),
        "lgbm_17_demand_only": _run(
            "lgbm_17_demand_only",
            backtest.run(series, _arm(series, bias=900.0), horizons=(1, 2, 3), cutoffs=cutoffs),
            features=list(arms_mod.ARMS["lgbm_17_demand_only"].expected_informative),
            refits=len(cutoffs),
        ),
        "chronos_bolt@ctx671": _run(
            "chronos_bolt@ctx671",
            backtest.run(
                series,
                _arm(series, bias=0.0, fails_on=hard),
                horizons=(1, 2, 3),
                cutoffs=cutoffs,
            ),
            context_hours=671,
        ),
    }

    artifact = compare.build_artifact(
        runs,
        cutoff_candidates=cutoffs,
        contiguity={},
        is_real=False,
        data_kind="synthetic_fixture",
        warning="SYNTHETIC FIXTURE, NOT a benchmark.",
    )

    assert artifact["failed_gate"] is None, artifact.get("failure")
    call = artifact["verdict"]["chronos_bolt@ctx671/lgbm_17_demand_only"]
    assert call["rule"] == imputation.IMPUTATION_RULE
    assert call["bands_agree"] is False, (
        "the band is supposed to move here; a reader could not tell this verdict "
        "from one that does not depend on an arbitrary rule"
    )
    subject = next(a for a in artifact["arms"] if a["id"] == "chronos_bolt@ctx671")
    assert subject["imputed_folds"] == len(hard)
    assert subject["mae"] > subject["mae_intersection"], (
        "the published `mae` is not the pessimistic one; a reader quoting `mae` "
        "would be quoting the flattered number"
    )


def test_an_artifact_without_the_naive_is_refused_rather_than_intersected(series, cutoffs):
    """The refusal is the point: silently falling back is how this defect began."""
    runs = {
        "lgbm_17_demand_only": _run(
            "lgbm_17_demand_only",
            backtest.run(series, _arm(series, bias=900.0), horizons=(1, 2, 3), cutoffs=cutoffs),
            features=list(arms_mod.ARMS["lgbm_17_demand_only"].expected_informative),
            refits=len(cutoffs),
        ),
    }

    artifact = compare.build_artifact(
        runs,
        cutoff_candidates=cutoffs,
        contiguity={},
        is_real=False,
        data_kind="synthetic_fixture",
    )

    assert artifact["failed_gate"] == "imputation"
    assert "seasonal_naive" in artifact["failure"]


def _run(arm_id: str, result: backtest.BacktestResult, **kwargs) -> compare.ArmRun:
    meter = cost.CostMeter()
    with meter.timing("infer"):
        pass
    defaults = {
        "features": [],
        "refits": 0,
        "fit_anchor_utc": None,
        "params": {},
        "in_domain_training_hours": 0,
    }
    return compare.ArmRun(
        arm_id=arm_id,
        result=result,
        cost=meter.block(len(result.predictions)),
        **{**defaults, **kwargs},
    )
