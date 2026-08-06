"""The comparison ladder, and the two gates that keep a rung honest.

A zero-shot univariate model against a GBM holding twenty-seven features is not a
comparison. The ladder in `models.arms` removes one kind of information per rung,
and these tests pin the two ways a rung can lie:

* it carries a feature its rung forbids (`assert_composition`);
* it declares hyperparameters the booster was not fitted with (`assert_params`),
  or a refit cadence it did not have (`assert_cadence`).

Both gates were built canary-first and both were seen green on the defect before
they were written this way — a composition check that watched only the
seventeen-feature arm let a twelve-feature arm through carrying thirteen, and a
params check comparing the caller's dict to the artifact's dict compared two
copies of the same claim.
"""

from __future__ import annotations

import pandas as pd
import pytest

from features import build as build_mod
from features import panel as panel_mod
from models import arms, backtest, fixtures, lgbm


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    """200 days, and the length is load-bearing.

    Over 40 days no US federal holiday falls in the window, so `is_holiday` is
    constant and indistinguishable from a blanked feature — which is exactly how
    the first version of the composition gate passed its own sabotage canary.
    Measured: `nunique() == 1` at 40 days, `== 2` at 200.
    """
    frame = fixtures.synthetic_series(days=200)
    return panel_mod.build_panel(
        frame["demand_mwh"], frame["temperature_c"], fixtures.synthetic_forecast(frame)
    )


@pytest.fixture(scope="module")
def design(panel) -> pd.DataFrame:
    origins = build_mod.training_origins(panel.index, stride_hours=24, max_horizon=24)
    return build_mod.build_design_matrix(panel, origins, tuple(range(1, 25)))


def test_the_ladder_removes_one_kind_of_information_per_rung():
    counts = {arm_id: len(spec.expected_informative) for arm_id, spec in arms.ARMS.items()}
    assert counts == {
        "lgbm_27": 27,
        "lgbm_20_no_fcst": 20,
        "lgbm_17_demand_only": 17,
        "lgbm_12_no_calendar": 12,
        "lgbm_12_frozen": 12,
    }


def test_the_no_forecast_rung_still_reads_a_thermometer():
    """The rung most likely to be mistaken for a univariate anchor, and why it is not.

    `mae_without_forecast_weather` is already measured and committed, so it is
    tempting as the fair comparison. It keeps observed temperature in three
    shapes, which a univariate model never sees.
    """
    kept = set(arms.ARMS["lgbm_20_no_fcst"].expected_informative)
    assert set(arms.OBSERVED_TEMPERATURE) <= kept
    assert set(arms.OBSERVED_TEMPERATURE).isdisjoint(
        arms.ARMS["lgbm_17_demand_only"].expected_informative
    )


def test_calendar_is_unreachable_by_dropping_panel_columns(panel):
    """Why `drop_features` had to exist: the old mechanism cannot reach calendar.

    `ablate_forecast_weather` drops columns from the *panel*. The panel does
    carry `month` and `is_weekend` — so a name-disjointness check would be
    wrong — but `build_design_matrix` never reads them: it recomputes the
    calendar from the target timestamp. Dropping them from the panel therefore
    changes nothing, and the panel-ablation floor stays at 17 features.
    """
    origins = build_mod.training_origins(panel.index, stride_hours=24, max_horizon=24)
    horizons = tuple(range(1, 25))

    with_calendar_columns = build_mod.build_design_matrix(panel, origins, horizons)
    shared = [c for c in build_mod.CALENDAR_FEATURES if c in panel.columns]
    assert shared, "the panel is expected to carry some calendar columns"
    without = build_mod.build_design_matrix(panel.drop(columns=shared), origins, horizons)

    for column in build_mod.CALENDAR_FEATURES:
        pd.testing.assert_series_equal(with_calendar_columns[column], without[column])


def test_blanking_keeps_the_layout_and_kills_the_information(panel):
    origins = build_mod.training_origins(panel.index, stride_hours=24, max_horizon=24)
    full = build_mod.build_design_matrix(panel, origins, tuple(range(1, 25)))
    blanked = build_mod.build_design_matrix(
        panel,
        origins,
        tuple(range(1, 25)),
        drop_features=arms.ARMS["lgbm_12_no_calendar"].drop_features,
    )

    assert list(blanked.columns) == list(full.columns)
    assert len(build_mod.informative_features(blanked)) == 12
    # The categoricals are blanked to a constant, not NaN: `feature_frame` casts
    # them to int16 and an all-NaN integer cast raises.
    frame = build_mod.feature_frame(blanked)
    for column in build_mod.CATEGORICAL_FEATURES:
        assert frame[column].nunique() == 1


def test_horizon_h_cannot_be_blanked(design):
    """It is the key of the direct multi-horizon design, not an ablatable feature."""
    with pytest.raises(ValueError, match=r"^`horizon_h` is the key"):
        build_mod.blank_features(design, ["horizon_h"])


def test_blanking_an_unknown_feature_is_refused(design):
    with pytest.raises(ValueError, match=r"^Not features of this design: \['nope'\]"):
        build_mod.blank_features(design, ["nope"])


def test_is_holiday_only_varies_on_a_long_enough_window(panel):
    """The measurement that forced the gate to stop inferring composition from data."""
    origins = build_mod.training_origins(panel.index, stride_hours=24, max_horizon=24)
    design = build_mod.build_design_matrix(panel, origins, tuple(range(1, 25)))
    assert design["is_holiday"].nunique() == 2, (
        "this fixture window contains no holiday, so a blanked `is_holiday` and an "
        "honest one are indistinguishable and the sabotage canary below proves nothing"
    )


def test_composition_gate_catches_an_arm_built_to_the_wrong_spec(panel):
    """Canary 1: a twelve-feature arm built carrying thirteen.

    `is_holiday` leaks back in — the most plausible slip, because it is the
    calendar feature that looks least like one.
    """
    origins = build_mod.training_origins(panel.index, stride_hours=24, max_horizon=24)
    sabotaged = tuple(
        f for f in arms.ARMS["lgbm_12_no_calendar"].drop_features if f != "is_holiday"
    )
    design = build_mod.build_design_matrix(
        panel, origins, tuple(range(1, 25)), drop_features=sabotaged
    )

    with pytest.raises(arms.ArmGateError) as excinfo:
        arms.assert_composition("lgbm_12_no_calendar", design, sabotaged)

    assert excinfo.value.gate == "arm-composition"
    assert "is_holiday" in str(excinfo.value)


def test_composition_gate_catches_a_declaration_the_frame_does_not_honour(panel):
    """Canary 2: the right spec declared, a different one applied.

    This is the half that a spec-only check cannot see, and it is the one that
    matters when the artifact is written from the declaration.
    """
    origins = build_mod.training_origins(panel.index, stride_hours=24, max_horizon=24)
    spec = arms.ARMS["lgbm_12_no_calendar"]
    applied = tuple(f for f in spec.drop_features if f != "is_holiday")
    design = build_mod.build_design_matrix(
        panel, origins, tuple(range(1, 25)), drop_features=applied
    )

    with pytest.raises(arms.ArmGateError, match="still carrying information"):
        arms.assert_composition("lgbm_12_no_calendar", design, spec.drop_features)


def test_composition_gate_is_silent_on_a_correct_arm(panel):
    """Negative control. A gate that fires on the honest case is not a gate."""
    origins = build_mod.training_origins(panel.index, stride_hours=24, max_horizon=24)
    spec = arms.ARMS["lgbm_12_no_calendar"]
    design = build_mod.build_design_matrix(
        panel, origins, tuple(range(1, 25)), drop_features=spec.drop_features
    )

    assert len(arms.assert_composition("lgbm_12_no_calendar", design, spec.drop_features)) == 12


def test_params_gate_reads_the_booster_not_the_declaration(design):
    """The canary: fitted with `num_leaves=31`, artifact declares 63."""
    booster = lgbm.train_booster(design, {"num_leaves": 31}, 10)

    with pytest.raises(arms.ArmGateError) as excinfo:
        arms.assert_params("lgbm_27", booster, {**lgbm.DEFAULT_PARAMS})

    assert excinfo.value.gate == "arm-params"
    assert "num_leaves" in str(excinfo.value)

    # Negative control: the declaration that matches the booster passes.
    arms.assert_params("lgbm_27", booster, {**lgbm.DEFAULT_PARAMS, "num_leaves": 31})


def test_cadence_gate_pins_the_frozen_anchor():
    first = pd.Timestamp("2026-06-02T12:00:00Z")
    other = pd.Timestamp("2026-07-01T12:00:00Z")

    arms.assert_cadence("lgbm_12_frozen", 1, first, first)  # negative control

    with pytest.raises(arms.ArmGateError, match="frozen arm reports 55"):
        arms.assert_cadence("lgbm_12_frozen", 55, first, first)

    with pytest.raises(arms.ArmGateError, match="anchored at"):
        arms.assert_cadence("lgbm_12_frozen", 1, other, first)

    with pytest.raises(arms.ArmGateError, match="only 1 refit"):
        arms.assert_cadence("lgbm_17_demand_only", 1, None, first)


def test_a_frozen_arm_fits_once_and_a_refit_arm_fits_every_fold(panel):
    series = panel[panel_mod.DEMAND_COLUMN]
    cutoffs = backtest.make_cutoffs(
        series.dropna().sort_index().index, 1, tuple(range(1, 25)), 12, 168
    )
    common = {
        "panel": panel,
        "horizons": tuple(range(1, 25)),
        "params": {"num_threads": 1},
        "num_boost_round": 20,
        "train_stride_hours": 24,
        "drop_features": arms.ARMS["lgbm_12_frozen"].drop_features,
    }

    frozen = lgbm.WalkForwardLightGBM(**common, freeze_at=cutoffs[0])
    refit = lgbm.WalkForwardLightGBM(**common)
    backtest.run(series, frozen, weeks=1, cutoffs=cutoffs)
    backtest.run(series, refit, weeks=1, cutoffs=cutoffs)

    assert frozen.fits == 1
    assert refit.fits == len(cutoffs)
    assert len(cutoffs) > 1, "a one-fold window would make the two indistinguishable"
