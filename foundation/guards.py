"""The two guards a foundation-model arm needs, and neither imports torch.

They live here rather than in the adapter for one reason: the CI job cannot
install torch, so a guard inside `foundation.tsfm` could only ever be tested by
skipping the test — and a skipped test reports green, which is the shape of
failure this whole lane exists to avoid.

**Contiguity (G2).** `models.backtest.run` calls `series.dropna()` before it
slices, so a gap does not arrive as NaN — it arrives as a *shorter index*. Every
model in this repo today reindexes by timestamp and is immune. A foundation
model consumes `history.to_numpy()`: position, not time. It would read a series
with a six-hour hole as six hours younger than it is and shift every daily and
weekly cycle it inferred by that much.

Two things the first design of this guard got wrong, both caught by running it:

* It reindexed to `history.index.max()`, which **cannot see a hole at the right
  edge** — the blackout still open at forecast time, which is the common case in
  a day-ahead setting. Measured: a six-hour hole ending at `cutoff - 1h` was
  reported as zero missing hours. The grid now ends at `cutoff - 1h`.
* Its budget was relative (1% of history). The history window expands, so the
  same sentence authorises 34 fabricated hours on the CI fixture and 162 on the
  real panel. The budget is absolute.

**Foresight (G3).** Not a value canary — a value canary is satisfied by
`if mae == 0.0`. An invariance probe: run the arm twice on two series that are
identical strictly before the cutoff and differ after it, and require the
predictions to be identical. An honest arm cannot see the difference.

Two things this got wrong too:

* Perturbing only the tail covers **one fold of fifty-five**. An arm that reads
  the future on folds 1-54 and behaves on fold 55 came out clean, with MAE 58
  against 2,551 for the seasonal naive. The probe runs per fold.
* Whether it caught anything at all depended on `>` versus `>=` at the
  perturbation boundary — a character the design never specified. It is `>=`
  here, and pinned by test.

The arm must be **rebuilt from the perturbed series**. An arm handed a closure
over the original series is unaffected by perturbing a copy, and even perfect
foresight comes out clean — measured.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from models import backtest

#: Total hours the guard will fabricate across the whole experiment series.
#: Absolute, so the sentence means the same thing on the fixture and on the
#: real panel.
MAX_IMPUTED_HOURS = 24
#: The longest single run of consecutive missing hours that may be interpolated.
#: Beyond this, linear interpolation of electricity demand is invention, and
#: this repository has a field named `is_real` precisely because it refuses that.
MAX_IMPUTED_RUN = 3


class LaneGateError(RuntimeError):
    """A lane gate refused. `gate` is what goes into the artifact's `failed_gate`."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(message)
        self.gate = gate


def _runs(missing: pd.DatetimeIndex) -> list[list[pd.Timestamp]]:
    runs: list[list[pd.Timestamp]] = []
    for stamp in missing:
        if runs and stamp - runs[-1][-1] == pd.Timedelta(hours=1):
            runs[-1].append(stamp)
        else:
            runs.append([stamp])
    return runs


def guard_contiguity(series: pd.Series, cutoffs: Sequence[pd.Timestamp]) -> tuple[pd.Series, dict]:
    """G2 — one gapless hourly series for **every** arm, or a refusal.

    Runs once, over the experiment series, before the arms fork. If the guard
    lived in the foundation adapter, then on the same missing hour the foundation
    model would receive an interpolated number while the GBM received NaN
    consumed natively — the arms would be scored on different data, which is the
    thing the fold contract exists to prevent.
    """
    series = series.dropna().sort_index()
    cutoffs = list(pd.DatetimeIndex(cutoffs))
    if not cutoffs:
        raise LaneGateError("contiguity", "No cutoffs: nothing to guard.")

    hour = pd.Timedelta(hours=1)
    # `name=` matters: `pd.date_range` produces an unnamed index, and reindexing
    # onto it silently drops `timestamp_utc` from a series the rest of the
    # pipeline keys on by name.
    grid = pd.date_range(series.index.min(), max(cutoffs) - hour, freq="h", name=series.index.name)
    missing = grid.difference(series.index)

    # The right edge, per cutoff. There is no interpolating an hour with nothing
    # after it, and this is the hole a day-ahead desk actually meets.
    touching = [c for c in cutoffs if (c - hour) in missing]
    if touching:
        raise LaneGateError(
            "contiguity",
            f"{len(touching)} cutoff(s) have no observation at cutoff-1h, "
            f"first {touching[0].isoformat()}: an open gap cannot be interpolated.",
        )

    runs = _runs(missing)
    longest = max((len(r) for r in runs), default=0)
    if longest > MAX_IMPUTED_RUN:
        raise LaneGateError(
            "contiguity",
            f"a run of {longest} consecutive missing hour(s) exceeds "
            f"MAX_IMPUTED_RUN={MAX_IMPUTED_RUN}; interpolating that is invention.",
        )
    if len(missing) > MAX_IMPUTED_HOURS:
        raise LaneGateError(
            "contiguity",
            f"{len(missing)} missing hour(s) exceed MAX_IMPUTED_HOURS={MAX_IMPUTED_HOURS}.",
        )

    # Repair the *history* region only, and hand back everything after it
    # untouched. The grid stops at `max(cutoffs) - 1h`; past that instant the
    # series is no longer context, it is the **actuals**, and interpolating an
    # actual fabricates the very thing being measured. A missing actual must stay
    # missing so `_is_scorable` drops that fold, which is the honest outcome.
    #
    # Returning only the grid was the first version, and it silently removed
    # every target hour: `backtest.run` then raised "Every fold was unscorable".
    repaired = series.reindex(grid).interpolate(method="time", limit_direction="both")
    tail = series[series.index > grid[-1]]
    return pd.concat([repaired, tail]), {
        "imputed_hours": len(missing),
        "imputed_runs": len(runs),
        "longest_imputed_run": longest,
        "grid_hours": len(grid),
        "actuals_untouched_from": grid[-1].isoformat(),
    }


def foresight_probe(
    make_arm: Callable[[pd.Series], object],
    series: pd.Series,
    cutoffs: Sequence[pd.Timestamp],
    *,
    horizons: tuple[int, ...] = backtest.DEFAULT_HORIZONS,
    sample: Sequence[pd.Timestamp] | None = None,
) -> dict:
    """G3 — the arm's forecast must not move when the future moves.

    `make_arm(series) -> predict_fn` is a factory, not an arm: the probe has to
    build the arm **from the perturbed series**, or an arm closing over the
    original is untouched and even perfect foresight scores clean.

    `sample` restricts which cutoffs are probed. Full coverage costs two extra
    backtest runs per fold; on a refit-per-fold GBM at real scale that is roughly
    91 minutes per arm, so the GBM arms are probed on a declared subset while the
    zero-shot arms — the ones with no leakage assertion of their own — are probed
    on all of them.
    """
    series = series.dropna().sort_index()
    probed = list(pd.DatetimeIndex(sample if sample is not None else cutoffs))
    caught: list[str] = []

    for cutoff in probed:
        shifted = series.copy()
        after = shifted.index >= cutoff
        if not after.any():
            raise LaneGateError("foresight", f"nothing after {cutoff}: the probe would be vacuous")
        # `>=`, not `>`. With `>` the target at exactly the cutoff stays intact,
        # and an arm reading it goes unseen — measured, on this very fixture.
        shifted[after] = shifted[after] * 1.5 + 5000.0

        honest = backtest.run(series, make_arm(series), horizons=horizons, cutoffs=[cutoff])
        moved = backtest.run(shifted, make_arm(shifted), horizons=horizons, cutoffs=[cutoff])
        if not np.allclose(
            honest.predictions["prediction"].to_numpy(),
            moved.predictions["prediction"].to_numpy(),
            equal_nan=True,
        ):
            caught.append(cutoff.isoformat())

    return {"probed": len(probed), "caught": caught, "clean": not caught}


def assert_no_foresight(arm_id: str, report: dict) -> None:
    """The refusal half of G3, so the caller cannot read the report and shrug."""
    if not report["clean"]:
        raise LaneGateError(
            "foresight",
            f"{arm_id}: forecast changed when only the post-cutoff future changed, "
            f"on {len(report['caught'])} of {report['probed']} probed fold(s); "
            f"first {report['caught'][0]}",
        )
