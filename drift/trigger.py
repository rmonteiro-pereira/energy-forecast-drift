"""Collapse the four drift sections into one structured retrain verdict.

The policy, and why it is not "retrain whenever PSI > 0.2"
----------------------------------------------------------
Distribution drift is a *leading* indicator, not proof of harm. Winter arrives
every year: temperature PSI goes through the roof, and a model with a
temperature feature and two years of history handles it fine. Retraining on
every PSI excursion means retraining constantly, which costs compute, churns
the registry, and — worse — trains on a window too short to have learned the
new regime, producing a champion that is *worse* than the one it replaced.

Performance drift is the opposite: it proves the model got worse, but it only
speaks once the actuals have arrived, which is hours-to-days late.

So the rules combine them:

  R1  performance drift alerts                      -> RETRAIN
      the model is measurably worse. Nothing else needs to be true.

  R2  a distribution signal alerts AND performance
      is at least `warn`                            -> RETRAIN
      a plausible cause plus a visible effect. This is the common real case.

  R3  two or more distribution signals alert        -> RETRAIN
      inputs *and* output (or target) both moved: a regime change the model
      has never been fitted on. Acting before the errors confirm it is the
      point of monitoring.

  R4  anything else non-`ok`                        -> WATCH
      recorded, charted, not acted on.

  R5  everything `ok`                               -> HEALTHY

The verdict is a structure, never a bare bool: `should_retrain`, the severity,
the rule that fired, every reason with its metric/threshold pair, and a
per-signal map. A pipeline can branch on one field; a human can audit the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from drift.config import DEFAULT_THRESHOLDS, DriftThresholds, Severity
from drift.detectors import INSUFFICIENT_DATA, DriftSection

DISTRIBUTION_TYPES = ("feature", "target", "prediction")

ACTION_RETRAIN = "retrain"
ACTION_WATCH = "watch"
ACTION_NONE = "none"


@dataclass(frozen=True)
class Reason:
    """One concrete fact that pushed the verdict — always metric vs threshold."""

    drift_type: str
    severity: Severity
    metric: str
    value: float | None
    threshold: float | None
    detail: str

    def as_dict(self) -> dict:
        return {
            "drift_type": self.drift_type,
            "severity": self.severity.value,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "detail": self.detail,
        }


@dataclass
class RetrainVerdict:
    """The structured answer to "should this model be retrained right now?"."""

    should_retrain: bool
    action: str
    severity: Severity
    rule: str
    rationale: str
    signals: dict[str, str]
    reasons: list[Reason] = field(default_factory=list)
    evaluated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    def as_dict(self) -> dict:
        return {
            "should_retrain": self.should_retrain,
            "action": self.action,
            "severity": self.severity.value,
            "rule": self.rule,
            "rationale": self.rationale,
            "signals": self.signals,
            "reasons": [r.as_dict() for r in self.reasons],
            "evaluated_at_utc": self.evaluated_at_utc,
        }


def _reason_for(section: DriftSection, thresholds: DriftThresholds) -> Reason:
    """Turn a section into the one metric/threshold pair that explains it."""
    if section.drift_type == "performance":
        return Reason(
            drift_type="performance",
            severity=section.severity,
            metric="mae_degradation",
            value=section.details.get("mae_degradation"),
            threshold=thresholds.mae_degradation_alert
            if section.severity is Severity.ALERT
            else thresholds.mae_degradation_warn,
            detail=section.summary,
        )
    return Reason(
        drift_type=section.drift_type,
        severity=section.severity,
        metric="psi",
        value=section.details.get("max_psi"),
        threshold=thresholds.psi_alert
        if section.severity is Severity.ALERT
        else thresholds.psi_warn,
        detail=section.summary,
    )


def evaluate(
    sections: dict[str, DriftSection],
    thresholds: DriftThresholds = DEFAULT_THRESHOLDS,
) -> RetrainVerdict:
    """Apply R1-R5 to the four sections and return the verdict."""
    severities = {name: section.severity for name, section in sections.items()}
    performance = severities.get("performance", Severity.OK)
    distribution_alerts = [t for t in DISTRIBUTION_TYPES if severities.get(t) is Severity.ALERT]

    # "OK" from `performance_drift` carries two very different meanings: the
    # error was measured and did not degrade, or there were too few scored rows
    # to measure it at all — the second returns OK with `status:
    # insufficient_data`. Only the first may be used to argue *against* a
    # retrain, so the distinction is made once, here, rather than at each use.
    performance_section = sections.get("performance")
    performance_is_measured = (
        performance_section is not None
        and performance_section.details.get("status") != INSUFFICIENT_DATA
    )
    performance_is_measured_and_clean = performance_is_measured and performance is Severity.OK

    overall = Severity.worst(severities.values())
    reasons = [
        _reason_for(section, thresholds)
        for section in sections.values()
        if section.severity is not Severity.OK
    ]
    reasons.sort(key=lambda r: r.severity.rank, reverse=True)
    signals = {name: severity.value for name, severity in severities.items()}

    def verdict(should_retrain: bool, action: str, rule: str, rationale: str) -> RetrainVerdict:
        return RetrainVerdict(
            should_retrain=should_retrain,
            action=action,
            severity=overall,
            rule=rule,
            rationale=rationale,
            signals=signals,
            reasons=reasons,
        )

    if performance is Severity.ALERT:
        return verdict(
            True,
            ACTION_RETRAIN,
            "R1_performance_alert",
            "The frozen model's rolling error crossed the degradation alert line. "
            "That is measured harm, so it triggers a retrain on its own.",
        )

    if distribution_alerts and performance is Severity.WARN:
        return verdict(
            True,
            ACTION_RETRAIN,
            "R2_distribution_alert_with_performance_warning",
            f"{', '.join(distribution_alerts)} drift is alerting and the error is already "
            "degrading: a plausible cause with a visible effect.",
        )

    if len(distribution_alerts) >= 2 and not performance_is_measured_and_clean:
        return verdict(
            True,
            ACTION_RETRAIN,
            "R3_multiple_distribution_alerts",
            f"{len(distribution_alerts)} distribution signals are alerting "
            f"({', '.join(distribution_alerts)}) — a regime the model was never fitted on, "
            "and the error is not measured well enough to contradict them. "
            "Acting before the errors confirm it is the point of monitoring.",
        )

    if len(distribution_alerts) >= 2:
        # Same evidence as R3, opposite conclusion, because the lagging
        # indicator is available here and disagrees. R3 used to fire on the
        # distribution signals alone, and on 2026-08-02 that made the published
        # verdict assert "the champion should be refit" while the very same
        # artifact measured the error 25.7% *better* than the reference window.
        #
        # That was a gap in the ladder rather than a threshold: R2 above
        # requires performance to be at least WARN before it will retrain on a
        # distribution signal, and R4 below says in its own words that a
        # distribution signal "without measured degradation is a leading
        # indicator, not proof of harm". R3 sat between them and skipped the
        # question entirely, which also left R2 with almost nothing to do.
        #
        # The signals are not suppressed — every one of them is still reported,
        # still charted, and the verdict is still not OK. What changes is the
        # action, because `retrain` is a claim about the model and that claim
        # was false. Inputs moving while the model tracks them is what a
        # seasonal series does.
        #
        # The guard is on *measured* and clean, not merely on "not alerting".
        # `performance_drift` returns severity OK with `status:
        # insufficient_data` when there are too few scored rows, so reading the
        # severity alone would silence exactly the label-free case R3 exists
        # for. Unknown is not safe, the same rule `drift.windows` applies to a
        # champion with no `train_data_end_utc`.
        return verdict(
            False,
            ACTION_WATCH,
            "R3b_distribution_without_measured_harm",
            f"{len(distribution_alerts)} distribution signals are alerting "
            f"({', '.join(distribution_alerts)}), but the frozen model's error was measured "
            "over the same windows and did not degrade. Inputs moved and the model tracked "
            "them: that is drift worth watching, not proof the champion needs refitting.",
        )

    if overall is not Severity.OK:
        return verdict(
            False,
            ACTION_WATCH,
            "R4_watch",
            "Drift is visible but no rule for retraining is satisfied: a single "
            "distribution signal without measured degradation is a leading indicator, "
            "not proof of harm. Recorded and charted, not acted on.",
        )

    return verdict(
        False,
        ACTION_NONE,
        "R5_healthy",
        "All four drift signals are within their thresholds.",
    )
