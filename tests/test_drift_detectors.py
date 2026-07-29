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
from drift.config import DEFAULT_THRESHOLDS, Severity
from drift.windows import NotEnoughHistoryError, build_windows
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
