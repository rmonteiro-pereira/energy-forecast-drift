"""The alarm must fire on a shift we injected, and stay silent when we did not.

That pair is the whole test of a drift detector. A detector that never fires is
useless; a detector that always fires is worse, because it trains people to
ignore it. So every injection test here has a mirror-image control running the
identical code path on the untouched fixture.

The shifts are injected by `drift.simulate`, which states exactly what it did in
data units — so a failure says "a +12,000 MW level shift did not raise target
PSI above 0.2", not "drift not detected".
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from drift import detectors, simulate, trigger
from drift.config import DEFAULT_CURRENT_DAYS, DEFAULT_THRESHOLDS, Severity
from drift.windows import NoPostTrainingData, NotEnoughHistoryError, build_windows
from features import build as build_mod
from features import panel as panel_mod
from models import fixtures

# Deliberately cheap: 12h origin stride and 60 boosting rounds. The detectors
# are what is under test, not the booster's accuracy, and the whole module then
# runs in seconds instead of minutes.
FAST = {"stride_hours": 12, "num_boost_round": 60}

# Large enough that no reasonable threshold could miss it (~12% of the fixture's
# base level), and stated here so the assertions can quote it.
SHIFT_MW = 12_000.0


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    frame = fixtures.synthetic_series(days=200)
    return panel_mod.build_panel(frame["demand_mwh"], frame["temperature_c"])


@pytest.fixture(scope="module")
def clean_windows(panel):
    """The control: the fixture exactly as generated, nothing injected."""
    return build_windows(panel, **FAST)


@pytest.fixture(scope="module")
def shifted_windows(panel):
    """The same pipeline after a +12,000 MW level shift over the current window."""
    shifted, _spec = simulate.inject_shift(
        panel, days_before_end=14, demand_offset_mw=SHIFT_MW, kind="level_shift"
    )
    return build_windows(shifted, **FAST)


@pytest.fixture(scope="module")
def clean_sections(clean_windows):
    return detectors.run_all(clean_windows, DEFAULT_THRESHOLDS)


@pytest.fixture(scope="module")
def shifted_sections(shifted_windows):
    return detectors.run_all(shifted_windows, DEFAULT_THRESHOLDS)


# ---------------------------------------------------------------------------
# the injection: the alarm must fire
# ---------------------------------------------------------------------------
def test_injected_level_shift_fires_every_drift_signal(shifted_sections):
    for name in ("feature", "target", "prediction", "performance"):
        assert shifted_sections[name].severity is Severity.ALERT, (
            f"a {SHIFT_MW:+,.0f} MW level shift left {name} drift at "
            f"{shifted_sections[name].severity.value}: {shifted_sections[name].summary}"
        )


def test_injected_level_shift_triggers_a_retrain(shifted_sections):
    verdict = trigger.evaluate(shifted_sections, DEFAULT_THRESHOLDS)
    assert verdict.should_retrain is True
    assert verdict.action == trigger.ACTION_RETRAIN
    # Measured degradation is present, so R1 must be the rule that fires — it is
    # the strongest evidence and is checked first.
    assert verdict.rule == "R1_performance_alert"
    assert verdict.reasons, "a retrain verdict must carry its reasons"


def test_injected_shift_pushes_target_psi_past_the_alert_line(shifted_sections):
    column = shifted_sections["target"].details["columns"][0]
    assert column["psi"]["psi"] > DEFAULT_THRESHOLDS.psi_alert
    assert column["distribution"]["mean_shift"] == pytest.approx(SHIFT_MW, rel=0.1)


def test_injected_shift_degrades_the_measured_error(shifted_sections, clean_sections):
    shifted = shifted_sections["performance"].details
    clean = clean_sections["performance"].details
    assert shifted["mae_degradation"] > DEFAULT_THRESHOLDS.mae_degradation_alert
    assert shifted["current"]["mae"] > clean["current"]["mae"]


# ---------------------------------------------------------------------------
# the control: the alarm must stay silent
# ---------------------------------------------------------------------------
def test_alarm_stays_silent_on_the_unshifted_fixture(clean_sections):
    verdict = trigger.evaluate(clean_sections, DEFAULT_THRESHOLDS)
    assert verdict.should_retrain is False
    assert verdict.action != trigger.ACTION_RETRAIN


def test_target_and_prediction_are_quiet_without_an_injected_shift(clean_sections):
    """No shift was injected, so neither the demand nor the forecast may alert.

    Feature drift is deliberately *not* asserted quiet: the fixture carries a
    real annual cycle, so June-vs-July temperature features move on their own.
    That is genuine input drift and the detector is right to report it — which
    is exactly why a single distribution signal does not trigger a retrain.
    """
    assert clean_sections["target"].severity is Severity.OK
    assert clean_sections["prediction"].severity is Severity.OK


def test_performance_is_stable_without_an_injected_shift(clean_sections):
    degradation = clean_sections["performance"].details["mae_degradation"]
    assert degradation < DEFAULT_THRESHOLDS.mae_degradation_warn
    assert clean_sections["performance"].severity is Severity.OK


# ---------------------------------------------------------------------------
# detector mechanics
# ---------------------------------------------------------------------------
def test_deterministic_calendar_columns_are_reported_but_never_vote(clean_sections):
    section = clean_sections["feature"]
    excluded = set(section.details["columns_excluded_deterministic"])
    assert "month" in excluded, "month is a pure calendar artifact of the window geometry"

    reported = {c["column"] for c in section.details["columns"]}
    assert excluded <= reported, "excluded columns must still appear in the artifact"
    assert section.details["max_psi_column"] not in excluded


def test_prediction_drift_needs_no_labels(shifted_windows):
    """The label-free claim is load-bearing, so it is tested by removing labels.

    Copies, not the shared fixture: a detector test must not leave the windows
    mutated for whatever runs next.
    """
    blinded = replace(
        shifted_windows,
        reference=shifted_windows.reference.assign(**{build_mod.TARGET_COLUMN: float("nan")}),
        current=shifted_windows.current.assign(**{build_mod.TARGET_COLUMN: float("nan")}),
    )
    section = detectors.prediction_drift(blinded, DEFAULT_THRESHOLDS)
    assert section.severity is Severity.ALERT


def test_rolling_error_series_spans_both_windows(clean_windows):
    daily = detectors.rolling_error_series(clean_windows)
    assert set(daily["window"]) == {"reference", "current"}
    assert daily["day"].is_monotonic_increasing
    assert daily["mae_rolling"].notna().all()


def test_windows_are_time_ordered_and_the_booster_never_saw_them(clean_windows, panel):
    split = clean_windows.split
    reference_start = pd.Timestamp(split["reference_start_utc"])
    current_start = pd.Timestamp(split["current_start_utc"])

    assert reference_start < current_start
    assert clean_windows.reference["target_utc"].min() >= reference_start
    assert clean_windows.reference["target_utc"].max() < current_start
    assert clean_windows.current["target_utc"].min() >= current_start
    assert split["rows"]["train"] > 0
    assert split["booster_source"] == "fitted_on_train_window"


def test_a_short_panel_is_refused_with_an_explanation():
    frame = fixtures.synthetic_series(days=20)
    short = panel_mod.build_panel(frame["demand_mwh"], frame["temperature_c"])
    with pytest.raises(NotEnoughHistoryError, match=r"warm-up|empty"):
        build_windows(short, **FAST)


def test_a_tiny_window_is_reported_as_insufficient_rather_than_scored():
    """Below `min_samples` a column must not produce a severity at all."""
    result = detectors.compare_column([1.0] * 10, [500.0] * 10, "toy", DEFAULT_THRESHOLDS)
    assert result["insufficient_data"] is True
    assert result["severity"] == Severity.OK.value


# ---------------------------------------------------------------------------
# window anchoring — drift is measured from the end of training, not from "now"
# ---------------------------------------------------------------------------
def test_windows_anchor_on_the_end_of_training_rather_than_the_wall_clock(panel):
    """Drift asks about the model, so the boundary is where the model stopped learning.

    Unanchored, both windows slide with the clock and the monitor answers "did
    the last fortnight differ from the one before it?" — a question about the
    calendar. Measured on 2026-08-02, that shipped a verdict reading "a regime
    the model was never fitted on" about two windows lying entirely inside the
    champion's own training set.
    """
    anchor = panel.index.max() - pd.Timedelta(days=10)
    anchored = build_windows(panel, anchor=anchor, **FAST)

    assert pd.Timestamp(anchored.split["current_start_utc"]) == anchor, (
        "the current window must begin exactly where the champion stopped learning"
    )
    assert anchored.current["target_utc"].min() >= anchor, (
        "the current window contains hours the model was trained on"
    )

    # And the reference is the tail of what it *did* learn, so the comparison is
    # "what it knows" against "what has happened since".
    reference_start = pd.Timestamp(anchored.split["reference_start_utc"])
    assert reference_start < anchor
    assert anchored.reference["target_utc"].max() < anchor


def test_without_an_anchor_the_old_wall_clock_split_is_unchanged(panel):
    """No champion, no `train_data_end_utc`, no anchor — the fallback must still work."""
    unanchored = build_windows(panel, **FAST)
    end = panel.index.max()

    expected = end - pd.Timedelta(days=DEFAULT_CURRENT_DAYS)
    assert pd.Timestamp(unanchored.split["current_start_utc"]) == expected


def test_a_champion_trained_to_the_end_of_the_panel_has_nothing_to_monitor(panel):
    """The state every retrain passes through, and it is healthy rather than an error.

    Immediately after a retrain there is no hour the champion did not learn
    from, so there is no drift to measure. The distinct exception is what lets
    the pipeline publish "nothing to monitor yet" instead of either failing or —
    far worse — scoring the model against its own training data.
    """
    # One hour past the last labelled target: nothing at all has arrived since
    # the champion stopped learning.
    with pytest.raises(NoPostTrainingData):
        build_windows(panel, anchor=panel.index.max() + pd.Timedelta(hours=1), **FAST)


def test_a_current_window_too_small_to_measure_is_not_a_verdict(panel):
    """Structure and policy are separated, and this is the policy half.

    Anchoring exactly at the end of the panel leaves a handful of rows rather
    than none, so `build_windows` builds them — but a handful is not enough to
    say anything, and scoring it would publish a drift verdict computed from
    noise. `DriftThresholds.min_samples` is the existing answer to "too few to
    speak", and `pipeline.daily` applies it to the current window for exactly
    that reason.
    """
    barely = build_windows(panel, anchor=panel.index.max(), **FAST)

    assert not barely.current.empty, "the premise of this test no longer holds"
    assert len(barely.current) < DEFAULT_THRESHOLDS.min_samples, (
        "a window this thin must fall under the min_samples floor, or the "
        "pipeline would treat it as measurable"
    )
