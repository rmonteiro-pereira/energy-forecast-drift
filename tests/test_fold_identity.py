"""Two arms are only comparable on the folds they both scored.

The repository asserted this in prose and checked it nowhere. `models.train.compare`
merged two `BacktestResult`s on `horizon_h` alone and produced a headline for arms
scored on 55 and 45 folds — `mae_delta_pct: 518.68`, `horizons_won: 0/24` — with no
error, no warning, and no `n` in the output. It never bit because the two models in
this repo are deterministic and never return NaN. The first model that can fail a
horizon would have published a comparison between two different experiments.

The tests below are the canaries, in the order the defect actually unfolds:

1. `cutoffs=` pins candidate origins — and **that is not enough**, because a fold is
   dropped whole when any horizon is unscorable, which depends on what the model
   returned. Pinning candidates and calling the folds identical is the mistake.
2. `compare` therefore refuses divergent fold sets outright.
3. `align_arms` re-scores every arm onto the intersection and reports the two ways an
   arm loses a fold **separately** — an arm that never failed still loses folds when
   another arm fails, and one counter cannot honestly carry both meanings.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import panel as panel_mod
from models import backtest, baseline, fixtures, train


@pytest.fixture(scope="module")
def series() -> pd.Series:
    frame = fixtures.synthetic_series(days=60)
    panel = panel_mod.build_panel(
        frame["demand_mwh"], frame["temperature_c"], fixtures.synthetic_forecast(frame)
    )
    return panel[panel_mod.DEMAND_COLUMN]


@pytest.fixture(scope="module")
def candidates(series: pd.Series) -> list[pd.Timestamp]:
    clean = series.dropna().sort_index()
    return backtest.make_cutoffs(clean.index, 4, backtest.DEFAULT_HORIZONS, 12, 168)


def _fails_on(cutoffs_to_fail: set[pd.Timestamp], horizon_index: int = 7):
    """A `predict_fn` that returns NaN at one horizon on the named cutoffs."""

    def predict(history: pd.Series, target_times: pd.DatetimeIndex, cutoff: pd.Timestamp):
        out = pd.Series(float(history.iloc[-1]), index=target_times)
        if cutoff in cutoffs_to_fail:
            out.iloc[horizon_index] = np.nan
        return out

    return predict


def test_pinned_cutoffs_survive_a_longer_warm_up(series, candidates):
    """The same literal candidates, two histories of different length, same folds.

    This is what `cutoffs=` is for: `make_cutoffs` derives its window from
    `index.min()/max()`, so two arms scored on panels of different length get two
    different answers and "the same folds" becomes a sentence.
    """
    trimmed = series[series.index >= series.index.min() + pd.Timedelta(days=5)]

    full = backtest.run(series, baseline.predict, cutoffs=candidates)
    short = backtest.run(trimmed, baseline.predict, cutoffs=candidates)

    assert full.folds == short.folds
    assert full.overall["n"] == short.overall["n"]


def test_pinned_cutoffs_do_not_equalise_the_folds_actually_used(series, candidates):
    """The mistake this whole module exists to prevent, stated as a test.

    Identical candidates, and the fold sets still diverge — because the discard is
    driven by the model's own output, downstream of anything a cutoff list controls.
    """
    failed = set(candidates[:3])

    clean = backtest.run(series, baseline.predict, cutoffs=candidates)
    flaky = backtest.run(series, _fails_on(failed), cutoffs=candidates)

    assert len(clean.folds) == len(candidates)
    assert len(flaky.folds) == len(candidates) - len(failed)
    assert set(clean.folds) != set(flaky.folds)


def test_compare_refuses_arms_scored_on_different_folds(series, candidates):
    clean = backtest.run(series, baseline.predict, cutoffs=candidates)
    flaky = backtest.run(series, _fails_on(set(candidates[:3])), cutoffs=candidates)

    with pytest.raises(train.FoldIdentityError, match="different folds"):
        train.compare(clean, flaky)


def test_compare_emits_n_and_folds(series, candidates):
    """The absence of `n` is what let the old comparison look like a comparison."""
    clean = backtest.run(series, baseline.predict, cutoffs=candidates)
    result = train.compare(clean, clean)

    assert result["n"] == clean.overall["n"]
    assert result["folds"] == len(clean.folds)


def test_align_arms_separates_the_two_ways_an_arm_loses_a_fold(series, candidates):
    """A clean arm has `skipped_folds == 0` and still loses folds. Both get reported.

    Collapsing these into one counter would report the baseline as having failed to
    score three folds it scored perfectly well.
    """
    failed = set(candidates[:3])
    arms = {
        "clean": backtest.run(series, baseline.predict, cutoffs=candidates),
        "flaky": backtest.run(series, _fails_on(failed), cutoffs=candidates),
    }

    aligned, record = train.align_arms(arms)

    assert len({r.overall["n"] for r in aligned.values()}) == 1
    assert len(record["folds_intersected"]) == len(candidates) - len(failed)

    clean_report = record["arms"]["clean"]
    assert clean_report["unscorable_by_own_failure"] == 0
    assert len(clean_report["folds_dropped_vs_intersection"]) == len(failed)
    assert set(clean_report["folds_dropped_vs_intersection"]) == {t.isoformat() for t in failed}

    flaky_report = record["arms"]["flaky"]
    assert flaky_report["unscorable_by_own_failure"] == len(failed)
    assert flaky_report["folds_dropped_vs_intersection"] == []

    # And the aligned arms are now comparable, which is the whole point.
    train.compare(aligned["clean"], aligned["flaky"])


def test_align_arms_raises_when_the_arms_share_no_fold(series, candidates):
    """Disjoint failures leave nothing to compare, and that is not a silent zero."""
    half = len(candidates) // 2
    arms = {
        "a": backtest.run(series, _fails_on(set(candidates[:half])), cutoffs=candidates),
        "b": backtest.run(series, _fails_on(set(candidates[half:])), cutoffs=candidates),
    }

    with pytest.raises(train.FoldIdentityError, match="share no fold"):
        train.align_arms(arms)


def test_rescore_filters_and_never_re_predicts(series, candidates):
    clean = backtest.run(series, baseline.predict, cutoffs=candidates)
    keep = clean.folds[:2]

    trimmed = backtest.rescore(clean, keep)

    assert trimmed.folds == list(keep)
    assert trimmed.overall["n"] == len(keep) * len(backtest.DEFAULT_HORIZONS)
    # Same rows, same numbers — only fewer of them.
    kept = clean.predictions[clean.predictions["cutoff_utc"].isin(keep)]
    pd.testing.assert_frame_equal(trimmed.predictions, kept)


def test_rescore_refuses_folds_the_run_never_scored(series, candidates):
    clean = backtest.run(series, baseline.predict, cutoffs=candidates)
    invented = [clean.folds[0] + pd.Timedelta(days=365)]

    with pytest.raises(ValueError, match=r"^Cannot rescore onto folds the run never scored: \["):
        backtest.rescore(clean, invented)


def test_rescore_refuses_an_empty_fold_set(series, candidates):
    """Anchored on the whole message, and that is not pedantry.

    `match=` is a `re.search`, so a loose fragment like `"empty fold set"` still
    matches after mutmut wraps the literal into `"XXCannot rescore onto an empty
    fold set.XX"` — the mutant survived this test until the pattern was anchored.
    A test that cannot tell the message from a corrupted copy of the message is
    not testing the message.
    """
    clean = backtest.run(series, baseline.predict, cutoffs=candidates)

    with pytest.raises(ValueError, match=r"^Cannot rescore onto an empty fold set\.$"):
        backtest.rescore(clean, [])
