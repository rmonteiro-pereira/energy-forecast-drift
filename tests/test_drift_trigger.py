"""The retrain policy, tested rule by rule with hand-built sections.

`drift.trigger` is the piece a pipeline branches on, and it is pure — sections
in, verdict out — so it can be tested without fitting anything. Each of R1-R5
gets a case, and so does each way of *not* firing, because "does not retrain on
a single distribution alert" is the property that keeps the alarm credible.
"""

from __future__ import annotations

import pytest

from drift.config import DEFAULT_THRESHOLDS, DriftThresholds, Severity
from drift.detectors import DriftSection
from drift.trigger import ACTION_NONE, ACTION_RETRAIN, ACTION_WATCH, evaluate


def sections(
    feature=Severity.OK, target=Severity.OK, prediction=Severity.OK, performance=Severity.OK
):
    """Four sections at the given severities, with plausible supporting numbers."""
    return {
        "feature": DriftSection("feature", feature, "f", {"max_psi": 0.31}),
        "target": DriftSection("target", target, "t", {"max_psi": 0.42}),
        "prediction": DriftSection("prediction", prediction, "p", {"max_psi": 0.27}),
        "performance": DriftSection("performance", performance, "perf", {"mae_degradation": 0.44}),
    }


def test_r5_healthy_when_everything_is_ok():
    verdict = evaluate(sections())
    assert verdict.should_retrain is False
    assert verdict.action == ACTION_NONE
    assert verdict.rule == "R5_healthy"
    assert verdict.severity is Severity.OK
    assert verdict.reasons == []


def test_r1_performance_alert_retrains_on_its_own():
    verdict = evaluate(sections(performance=Severity.ALERT))
    assert verdict.should_retrain is True
    assert verdict.rule == "R1_performance_alert"


def test_r2_distribution_alert_plus_performance_warning_retrains():
    verdict = evaluate(sections(feature=Severity.ALERT, performance=Severity.WARN))
    assert verdict.should_retrain is True
    assert verdict.rule == "R2_distribution_alert_with_performance_warning"


def test_r3_two_distribution_alerts_retrain_before_the_errors_confirm_it():
    verdict = evaluate(sections(target=Severity.ALERT, prediction=Severity.ALERT))
    assert verdict.should_retrain is True
    assert verdict.rule == "R3_multiple_distribution_alerts"
    assert verdict.signals["performance"] == "ok"


def test_r4_a_single_distribution_alert_is_watched_not_acted_on():
    """The property that keeps the alarm credible: leading indicators only watch."""
    verdict = evaluate(sections(feature=Severity.ALERT))
    assert verdict.should_retrain is False
    assert verdict.action == ACTION_WATCH
    assert verdict.rule == "R4_watch"
    assert verdict.severity is Severity.ALERT  # loud, but not actionable


def test_r4_covers_warnings_that_never_reach_an_alert():
    verdict = evaluate(sections(feature=Severity.WARN, performance=Severity.WARN))
    assert verdict.should_retrain is False
    assert verdict.rule == "R4_watch"


def test_the_verdict_is_a_structure_not_a_boolean():
    verdict = evaluate(sections(performance=Severity.ALERT, feature=Severity.WARN)).as_dict()
    assert set(verdict) == {
        "should_retrain",
        "action",
        "severity",
        "rule",
        "rationale",
        "signals",
        "reasons",
        "evaluated_at_utc",
    }
    assert verdict["action"] == ACTION_RETRAIN
    assert set(verdict["signals"]) == {"feature", "target", "prediction", "performance"}


def test_every_reason_carries_its_metric_and_the_threshold_it_crossed():
    verdict = evaluate(sections(performance=Severity.ALERT, target=Severity.ALERT))
    assert len(verdict.reasons) == 2
    for reason in verdict.reasons:
        payload = reason.as_dict()
        assert payload["value"] is not None
        assert payload["threshold"] is not None
        assert payload["detail"]

    performance = next(r for r in verdict.reasons if r.drift_type == "performance")
    assert performance.metric == "mae_degradation"
    assert performance.threshold == DEFAULT_THRESHOLDS.mae_degradation_alert


def test_reasons_are_ordered_worst_first():
    verdict = evaluate(sections(feature=Severity.WARN, performance=Severity.ALERT))
    assert [r.severity for r in verdict.reasons] == [Severity.ALERT, Severity.WARN]


def test_thresholds_come_from_config_so_a_stricter_policy_changes_the_verdict():
    strict = DriftThresholds(mae_degradation_alert=0.10)
    section = sections(performance=Severity.ALERT)
    assert evaluate(section, strict).reasons[0].threshold == 0.10


def test_severity_ordering_is_explicit():
    assert Severity.OK.rank < Severity.WARN.rank < Severity.ALERT.rank
    assert Severity.worst([Severity.OK, Severity.ALERT, Severity.WARN]) is Severity.ALERT
    assert Severity.worst([]) is Severity.OK


@pytest.mark.parametrize(
    ("psi", "expected"),
    [(0.0, Severity.OK), (0.05, Severity.OK), (0.10, Severity.WARN), (0.2, Severity.ALERT)],
)
def test_psi_severity_reads_the_configured_lines(psi, expected):
    assert DEFAULT_THRESHOLDS.psi_severity(psi) is expected


def test_thresholds_are_overridable_from_the_environment(monkeypatch):
    monkeypatch.setenv("DRIFT_PSI_ALERT", "0.35")
    monkeypatch.setenv("DRIFT_MAE_DEGRADATION_ALERT", "0.5")
    thresholds = DriftThresholds.from_env()
    assert thresholds.psi_alert == 0.35
    assert thresholds.mae_degradation_alert == 0.5
    assert thresholds.psi_warn == DEFAULT_THRESHOLDS.psi_warn  # untouched keys keep defaults
