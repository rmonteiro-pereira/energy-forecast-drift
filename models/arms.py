"""The comparison arms, derived rather than declared.

A zero-shot foundation model receives one thing: the demand series. The GBM in
this repo receives twenty-seven features, seven of which are published weather
forecasts worth 40.89% of its MAE (`metrics/model.json`, `ablation`). Scoring
those two against each other measures the absence of covariates, not the models,
and the headline would be arithmetic that was already known.

So the arms are a ladder, and each rung removes exactly one kind of information:

    lgbm_27              27  everything, including forecast weather
    lgbm_20_no_fcst      20  no forecast weather — still sees *observed* temperature
    lgbm_17_demand_only  17  no weather at all — demand and calendar
    lgbm_12_no_calendar  12  demand only, refit every fold
    lgbm_12_frozen       12  demand only, fitted once

`lgbm_20_no_fcst` is the rung most likely to be mistaken for a fair anchor and is
not one: `temp_lag_168h`, `temp_last_1h` and `temp_roll_mean_24h` survive it, so
it still reads a thermometer the univariate model never sees.

Two things here are gates rather than helpers, because both were shown green on
the defect they exist to catch before they were written this way:

* `assert_composition` derives the expected feature set from `features.build`
  instead of comparing against a literal. A gate that watched only one arm let a
  twelve-feature arm through carrying thirteen.
* `assert_params` reads the **trained booster**, not the caller's dict. Comparing
  a declared dict against another declared dict passes while the model behind it
  was fitted with something else entirely.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import lightgbm as lgb
import pandas as pd

from features import build as build_mod

#: Observed temperature, in the three shapes the panel exposes it. Not forecast
#: weather — these are measurements of the past, and they are what makes
#: `lgbm_20_no_fcst` a poor stand-in for a univariate model.
OBSERVED_TEMPERATURE = ("temp_lag_168h", "temp_last_1h", "temp_roll_mean_24h")

_NO_FORECAST = tuple(build_mod.FORECAST_FEATURES)
_NO_WEATHER = _NO_FORECAST + OBSERVED_TEMPERATURE
_DEMAND_ONLY = _NO_WEATHER + tuple(build_mod.CALENDAR_FEATURES)


class ArmGateError(RuntimeError):
    """An arm does not match its specification. Carries the gate that refused it."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(message)
        self.gate = gate


@dataclass(frozen=True)
class ArmSpec:
    arm_id: str
    drop_features: tuple[str, ...]
    frozen: bool = False

    @property
    def expected_informative(self) -> tuple[str, ...]:
        """Derived from `features.build`, so a feature added upstream is not silently missed."""
        return tuple(f for f in build_mod.FEATURE_COLUMNS if f not in set(self.drop_features))


ARMS: dict[str, ArmSpec] = {
    spec.arm_id: spec
    for spec in (
        ArmSpec("lgbm_27", ()),
        ArmSpec("lgbm_20_no_fcst", _NO_FORECAST),
        ArmSpec("lgbm_17_demand_only", _NO_WEATHER),
        ArmSpec("lgbm_12_no_calendar", _DEMAND_ONLY),
        ArmSpec("lgbm_12_frozen", _DEMAND_ONLY, frozen=True),
    )
}


def _is_blank(column: pd.Series) -> bool:
    """A feature carrying nothing: all-null, or a single repeated value."""
    return not column.notna().any() or column.nunique(dropna=True) <= 1


def assert_composition(arm_id: str, design: pd.DataFrame, applied_drop: Sequence[str]) -> list[str]:
    """G13 — the arm carries exactly the features its rung allows.

    Two checks, because either one alone is satisfiable without the other.

    **The declared set matches the spec.** This is the authoritative half. The
    first version of this gate inferred the composition from the data — it
    counted features that were not all-null and not constant — and that cannot
    tell a blanked feature from one that happens not to vary. Measured:
    `is_holiday` has `nunique() == 1` over a 40-day fixture window because no US
    federal holiday falls in it, and `nunique() == 2` over 200 days. So the
    sabotage canary (a twelve-feature arm built carrying thirteen) passed the
    data-inferred gate on the short window, silently, for a reason that had
    nothing to do with the sabotage.

    **The frame agrees with the declaration.** A caller that declares the right
    drop set and applies a different one is caught here — every feature it says
    it dropped has to actually be blank in the design.

    Neither half is redundant: the first catches an arm built to the wrong spec,
    the second catches a spec that was declared and not honoured.
    """
    spec = ARMS[arm_id]
    declared = set(applied_drop)
    expected = set(spec.drop_features)
    if declared != expected:
        extra = sorted(declared - expected)
        missing = sorted(expected - declared)
        raise ArmGateError(
            "arm-composition",
            f"{arm_id}: dropped {len(declared)} features, spec says {len(expected)}"
            + (f"; unexpectedly dropped={extra}" if extra else "")
            + (f"; not dropped={missing}" if missing else ""),
        )

    not_blank = sorted(f for f in declared if not _is_blank(design[f]))
    if not_blank:
        raise ArmGateError(
            "arm-composition",
            f"{arm_id}: declared as dropped but still carrying information: {not_blank}",
        )

    return list(spec.expected_informative)


def assert_params(arm_id: str, booster: lgb.Booster, declared: dict) -> None:
    """G12 — what the artifact declares is what the booster was fitted with.

    `booster.params` is the trained object's own record. Checking the caller's
    dict against the artifact's dict compares two copies of the same claim and
    can never disagree with reality.
    """
    mismatches = {
        key: (booster.params.get(key), value)
        for key, value in declared.items()
        if key in booster.params and booster.params.get(key) != value
    }
    if mismatches:
        detail = "; ".join(
            f"{k}: booster={real!r} != declared={decl!r}" for k, (real, decl) in mismatches.items()
        )
        raise ArmGateError("arm-params", f"{arm_id}: {detail}")


def assert_cadence(arm_id: str, refits: int, fit_anchor_utc, first_candidate) -> None:
    """G12 (cadence half) — a frozen arm fits once, at the pinned anchor.

    The anchor is not cosmetic. A booster frozen at the first candidate and one
    frozen halfway through the window are different models with the same name.
    """
    spec = ARMS[arm_id]
    if spec.frozen:
        if refits != 1:
            raise ArmGateError("arm-cadence", f"{arm_id}: frozen arm reports {refits} refit(s)")
        if pd.Timestamp(fit_anchor_utc) != pd.Timestamp(first_candidate):
            raise ArmGateError(
                "arm-cadence",
                f"{arm_id}: fit anchored at {fit_anchor_utc}, expected {first_candidate}",
            )
    elif refits <= 1:
        raise ArmGateError(
            "arm-cadence", f"{arm_id}: refit-per-fold arm reports only {refits} refit(s)"
        )
