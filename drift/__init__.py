"""Drift detection (M4) — four drift types, own statistics, one retrain verdict.

`drift.stats` implements PSI and the two-sample Kolmogorov-Smirnov test from
scratch (no scipy at runtime); `drift.detectors` turns those into the four
sections the monitoring literature actually distinguishes — feature, target,
prediction and performance drift; `drift.trigger` collapses them into a single
structured verdict; `drift.run` is the entrypoint that writes `metrics/drift.json`.
"""

from drift.config import DEFAULT_THRESHOLDS, DriftThresholds, Severity

__all__ = ["DEFAULT_THRESHOLDS", "DriftThresholds", "Severity"]
