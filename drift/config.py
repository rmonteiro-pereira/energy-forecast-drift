"""Every drift threshold in one place — nothing is hardcoded at a call site.

Thresholds are the part of a drift system that gets tuned in production, so
they live in a single frozen dataclass that can be overridden from the
environment (`DRIFT_PSI_ALERT=0.15 ...`) and is serialised verbatim into
`metrics/drift.json`. A number that fired an alarm is therefore always
recoverable from the artifact that reports it.

Where the defaults come from
----------------------------
* **PSI 0.10 / 0.25** is the classic credit-scoring rule of thumb (Siddiqi):
  below 0.10 "no significant shift", 0.10-0.25 "moderate", above 0.25 "major".
  The spec for this project asks for the stricter 0.20 alert line, so that is
  what is used — a demand forecaster is refit cheaply and often, and it is
  better to look at a 0.2 than to miss it.
* **KS p < 0.01** rather than the reflexive 0.05: with ~2-3k rows per window
  and ~20 features, a 0.05 line flags something on nearly every run. The KS
  p-value is a *supporting* signal here, never the sole trigger.
* **MAE degradation 15% / 30%** relative to the reference window. Anything
  smaller is inside the fold-to-fold noise of an hourly load series.

Severity vocabulary
-------------------
`ok` < `warn` < `alert`. Only `alert` can move the retrain verdict on its own,
and even then only under the rules spelled out in `drift.trigger`.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Ordered severity. `StrEnum` so it serialises to JSON as its value."""

    OK = "ok"
    WARN = "warn"
    ALERT = "alert"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]

    @classmethod
    def worst(cls, severities: Iterable[Severity]) -> Severity:
        """The highest severity in `severities`, `ok` when the iterable is empty."""
        return max(severities, key=lambda s: s.rank, default=cls.OK)


_SEVERITY_RANK = {Severity.OK: 0, Severity.WARN: 1, Severity.ALERT: 2}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class DriftThresholds:
    """Thresholds for all four drift types.

    Distribution drift (feature / target / prediction) is judged on PSI, with
    the KS p-value as a second opinion; performance drift is judged on the
    *relative* degradation of rolling MAE and the absolute movement of MAPE.
    """

    # --- distribution drift ------------------------------------------------
    psi_warn: float = 0.10
    psi_alert: float = 0.20
    ks_p_alert: float = 0.01
    psi_bins: int = 10
    # A column with at most this many distinct reference values is binned by
    # category share instead of by quantile (hour, day-of-week, month, ...).
    max_categorical_levels: int = 24
    # Below this many rows a window is reported as `insufficient_data` rather
    # than scored — a PSI over 50 points is noise, not a signal.
    min_samples: int = 200
    # Share of feature columns that must alert before the *section* alerts.
    drifted_share_warn: float = 0.15
    drifted_share_alert: float = 0.30

    # --- performance drift -------------------------------------------------
    # Relative increase of MAE, current window vs reference window.
    mae_degradation_warn: float = 0.15
    mae_degradation_alert: float = 0.30
    # Absolute movement of MAPE, in percentage points.
    mape_degradation_warn_pp: float = 0.50
    mape_degradation_alert_pp: float = 1.00
    # Width of the rolling error window, in hours (168h = 7 days).
    rolling_window_hours: int = 168

    @classmethod
    def from_env(cls) -> DriftThresholds:
        """Defaults, with any `DRIFT_*` environment override applied."""
        return cls(
            psi_warn=_env_float("DRIFT_PSI_WARN", cls.psi_warn),
            psi_alert=_env_float("DRIFT_PSI_ALERT", cls.psi_alert),
            ks_p_alert=_env_float("DRIFT_KS_P_ALERT", cls.ks_p_alert),
            psi_bins=_env_int("DRIFT_PSI_BINS", cls.psi_bins),
            max_categorical_levels=_env_int(
                "DRIFT_MAX_CATEGORICAL_LEVELS", cls.max_categorical_levels
            ),
            min_samples=_env_int("DRIFT_MIN_SAMPLES", cls.min_samples),
            drifted_share_warn=_env_float("DRIFT_DRIFTED_SHARE_WARN", cls.drifted_share_warn),
            drifted_share_alert=_env_float("DRIFT_DRIFTED_SHARE_ALERT", cls.drifted_share_alert),
            mae_degradation_warn=_env_float("DRIFT_MAE_DEGRADATION_WARN", cls.mae_degradation_warn),
            mae_degradation_alert=_env_float(
                "DRIFT_MAE_DEGRADATION_ALERT", cls.mae_degradation_alert
            ),
            mape_degradation_warn_pp=_env_float(
                "DRIFT_MAPE_DEGRADATION_WARN_PP", cls.mape_degradation_warn_pp
            ),
            mape_degradation_alert_pp=_env_float(
                "DRIFT_MAPE_DEGRADATION_ALERT_PP", cls.mape_degradation_alert_pp
            ),
            rolling_window_hours=_env_int("DRIFT_ROLLING_WINDOW_HOURS", cls.rolling_window_hours),
        )

    def psi_severity(self, psi: float) -> Severity:
        """`alert` above the alert line, `warn` above the warn line, else `ok`."""
        if psi >= self.psi_alert:
            return Severity.ALERT
        if psi >= self.psi_warn:
            return Severity.WARN
        return Severity.OK

    def as_dict(self) -> dict:
        return asdict(self)


# --- window geometry ---------------------------------------------------------
# How the history is cut into "the model was fitted here" / "this is normal" /
# "this is what we are monitoring". Reference and current are both *out of
# sample* for the frozen booster, which is what makes the performance
# comparison between them meaningful.
DEFAULT_REFERENCE_DAYS = 28
DEFAULT_CURRENT_DAYS = 14

DEFAULT_THRESHOLDS = DriftThresholds()
