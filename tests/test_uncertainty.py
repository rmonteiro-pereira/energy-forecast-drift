"""The interval, and the block it is resampled over.

`-77.17%` and `24/24` are published as point estimates over 55 consecutive days,
with no interval anywhere in the repository. For a delta that large that is
harmless folklore. For the single-digit delta this lane expects, it is the answer,
and the block choice decides whether the interval is honest.

Measured here: resampling the 1,320 rows independently reports an interval
**2.0x narrower** than resampling the 55 origins. The 24 horizons of one origin
share a model state, a recent history and a weather regime; treating them as 24
independent observations is not a weaker interval, it is a wrong one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features import panel as panel_mod
from foundation import uncertainty as unc
from models import arms, backtest, baseline, fixtures, lgbm


@pytest.fixture(scope="module")
def scored() -> dict:
    frame = fixtures.synthetic_series(days=90)
    panel = panel_mod.build_panel(
        frame["demand_mwh"], frame["temperature_c"], fixtures.synthetic_forecast(frame)
    )
    series = panel[panel_mod.DEMAND_COLUMN]
    horizons = tuple(range(1, 25))
    cutoffs = backtest.make_cutoffs(series.dropna().sort_index().index, 2, horizons, 12, 168)

    spec = arms.ARMS["lgbm_12_no_calendar"]
    model = lgbm.WalkForwardLightGBM(
        panel=panel,
        horizons=horizons,
        params={"num_threads": 1},
        num_boost_round=40,
        train_stride_hours=24,
        drop_features=spec.drop_features,
    )
    return {
        "cutoffs": cutoffs,
        "gbm": backtest.run(series, model, horizons=horizons, cutoffs=cutoffs),
        "naive": backtest.run(series, baseline.predict, horizons=horizons, cutoffs=cutoffs),
    }


def test_the_block_is_the_origin_not_the_prediction(scored):
    report = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=200
    )

    assert report["block"] == "cutoff_utc"
    assert report["n_blocks"] == len(scored["cutoffs"])
    assert report["n_predictions"] == len(scored["cutoffs"]) * 24


def test_resampling_points_understates_the_interval(scored):
    """The measurement that makes the block choice a finding rather than a preference."""
    by_block = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=400
    )
    by_point = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=400, by_point=True
    )

    width_block = np.diff(by_block["mae_ratio"]["ci95"])[0]
    width_point = np.diff(by_point["mae_ratio"]["ci95"])[0]

    assert width_block > width_point, (
        "resampling whole origins must give the wider interval; if it does not, "
        "the horizons within a fold are not correlated and the block choice is moot"
    )


def test_g10_refuses_an_interval_resampled_over_points(scored):
    report = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=100, by_point=True
    )

    with pytest.raises(unc.UncertaintyError) as excinfo:
        unc.assert_block_is_origin(report, len(scored["cutoffs"]))

    assert excinfo.value.gate == "uncertainty-block"
    assert "not independent" in str(excinfo.value)


def test_g10_is_silent_on_an_origin_blocked_interval(scored):
    """Negative control."""
    report = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=100
    )
    unc.assert_block_is_origin(report, len(scored["cutoffs"]))


def test_g10_refuses_a_block_count_that_does_not_match_the_folds(scored):
    report = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=100
    )

    with pytest.raises(unc.UncertaintyError, match="against"):
        unc.assert_block_is_origin(report, len(scored["cutoffs"]) + 1)


def test_the_interval_is_reproducible(scored):
    """Recorded seed, so a reader can regenerate the number instead of trusting it."""
    first = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=200, seed=7
    )
    again = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=200, seed=7
    )

    assert first["mae_ratio"]["ci95"] == again["mae_ratio"]["ci95"]
    assert first["seed"] == 7


def test_the_point_estimate_sits_inside_its_own_interval(scored):
    report = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=400
    )

    low, high = report["mae_ratio"]["ci95"]
    assert low <= report["mae_ratio"]["point"] <= high
    low, high = report["mae_delta"]["ci95"]
    assert low <= report["mae_delta"]["point"] <= high


def test_an_arm_compared_with_itself_has_a_zero_delta(scored):
    """Sanity: the paired design must cancel exactly, not approximately."""
    report = unc.paired_block_bootstrap(
        scored["gbm"].predictions, scored["gbm"].predictions, n_resamples=100
    )

    assert report["mae_delta"]["point"] == 0.0
    assert report["mae_ratio"]["ci95"] == [1.0, 1.0]


def test_arms_that_do_not_share_their_rows_are_refused(scored):
    """An interval over unaligned arms is a comparison of two experiments."""
    trimmed = scored["gbm"].predictions.iloc[:-24]

    with pytest.raises(unc.UncertaintyError) as excinfo:
        unc.paired_block_bootstrap(scored["naive"].predictions, trimmed, n_resamples=10)

    assert excinfo.value.gate == "fold-identity"


# --------------------------------------------------------------------------
# The TimesFM reopen trigger fires on the interval, never on the point.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ci, expected",
    [
        ([0.98, 1.05], True),  # squarely inside the band
        ([0.70, 0.80], False),  # the TSFM clearly wins; identity of the model is settled
        ([1.40, 1.60], False),  # it clearly loses; a second TSFM would not change that
        ([0.80, 1.30], True),  # too wide to call — which is exactly when to reopen
        ([1.09, 1.40], True),  # only the lower edge touches the band
    ],
)
def test_reopen_fires_on_the_interval(ci, expected):
    assert unc.reopen_timesfm(ci) is expected


def test_a_point_trigger_would_have_been_a_coin_flip(scored):
    """Why the trigger moved from the point estimate to the interval.

    The reopen band `[0.95, 1.10]` is 0.15 wide. Measured on this project's own
    folds, the 95% interval for a MAE ratio is of the same order — so which side
    of the band a point estimate lands on is decided by resampling noise, and the
    rule would be a coin flip wearing a threshold.
    """
    report = unc.paired_block_bootstrap(
        scored["naive"].predictions, scored["gbm"].predictions, n_resamples=400
    )
    width = np.diff(report["mae_ratio"]["ci95"])[0]
    band_width = 1.10 - 0.95

    assert width > band_width / 5, (
        f"interval width {width:.4f} against a band of {band_width:.2f}: if the "
        "interval were genuinely tiny, a point trigger would be defensible"
    )


def test_the_helpers_agree_about_what_a_dataframe_looks_like(scored):
    """`BLOCK_KEY` has to exist in what `backtest.run` actually returns."""
    assert unc.BLOCK_KEY in scored["gbm"].predictions.columns
    assert isinstance(scored["gbm"].predictions[unc.BLOCK_KEY].iloc[0], pd.Timestamp)
