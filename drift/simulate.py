"""Inject a known distribution shift into a panel — for tests and for the demo.

A drift detector that has never been shown drift is untested. There is no real
drift episode to point at yet (no EIA key, and even with one a real episode
takes weeks to arrive), so the alarm is exercised against **synthetic shifts
with a known ground truth**: the tests here shift a window by a stated amount
and assert the alarm fires, then run the identical pipeline on the unshifted
panel and assert it stays silent.

HONESTY
-------
Nothing in this module ever runs by default. `drift.run` only calls it behind an
explicit `--simulate-shift` flag, and when it does, the resulting artifact
carries a `simulated_shift` block naming the shift — so a simulated episode can
never be mistaken for an observed one. The committed `metrics/drift.json` is
produced without it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from features.panel import DEMAND_COLUMN, TEMPERATURE_COLUMN


@dataclass(frozen=True)
class ShiftSpec:
    """What was done to the panel, in units a reader can check."""

    kind: str
    start_utc: str
    demand_offset_mw: float = 0.0
    demand_scale: float = 1.0
    temperature_offset_c: float = 0.0
    note: str = ""

    def as_dict(self) -> dict:
        return {
            **asdict(self),
            "warning": (
                "SIMULATED. This shift was injected on purpose to exercise the "
                "detectors; it is not an observed drift episode."
            ),
        }


def inject_shift(
    panel: pd.DataFrame,
    *,
    start: pd.Timestamp | None = None,
    days_before_end: int | None = None,
    demand_offset_mw: float = 0.0,
    demand_scale: float = 1.0,
    temperature_offset_c: float = 0.0,
    kind: str = "level_shift",
    note: str = "",
) -> tuple[pd.DataFrame, ShiftSpec]:
    """Return a copy of `panel` with a shift applied from `start` onwards.

    Either `start` or `days_before_end` must be given. The shift is applied to
    demand as ``y -> y * demand_scale + demand_offset_mw`` and to temperature as
    an offset, which between them cover the two episodes worth simulating:

    * a **level shift** (a large new load joins the balancing authority, or a
      respondent restates its series) — the target and the demand-lag features
      move together, and the frozen model is biased from the first hour;
    * a **weather regime shift** (an unprecedented heatwave) — the temperature
      features move first, demand follows through the model's thermal response,
      and the errors degrade only where the response is mis-specified.
    """
    if start is None:
        if days_before_end is None:
            raise ValueError("Pass either `start` or `days_before_end`.")
        start = panel.index.max() - pd.Timedelta(days=days_before_end)

    shifted = panel.copy()
    mask = shifted.index >= start

    if DEMAND_COLUMN in shifted.columns:
        shifted.loc[mask, DEMAND_COLUMN] = (
            shifted.loc[mask, DEMAND_COLUMN] * demand_scale + demand_offset_mw
        )
    if temperature_offset_c and TEMPERATURE_COLUMN in shifted.columns:
        shifted.loc[mask, TEMPERATURE_COLUMN] += temperature_offset_c

    spec = ShiftSpec(
        kind=kind,
        start_utc=pd.Timestamp(start).isoformat(),
        demand_offset_mw=float(demand_offset_mw),
        demand_scale=float(demand_scale),
        temperature_offset_c=float(temperature_offset_c),
        note=note,
    )
    return shifted, spec
