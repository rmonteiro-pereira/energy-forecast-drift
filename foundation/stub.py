"""A foundation-model-shaped forecaster with no foundation model in it.

This is what the CI job actually exercises, and saying so plainly matters more
than the code: **the stub proves the contract, not the model.** The smallest
usable Chronos-Bolt checkpoint is 34,622,352 bytes, 6.6x the repository's size
ceiling, and the test job touches no network — so no run inside CI can involve
real weights. What CI can prove is that the seam, the guards and the arm
bookkeeping behave; the number only exists after the dispatch run.

The stub is deliberately **positional**. It consumes `history.to_numpy()` and
indexes backwards by offset, exactly as a real TSFM adapter does, because that
is the property the contiguity guard exists to protect and a timestamp-indexed
stub would quietly not exercise it.

It is also deliberately honest: it reads nothing at or after the cutoff, so the
foresight probe must come back clean on it. A stub that could not pass its own
negative control would make every positive result meaningless.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

NAME = "stub_seasonal_positional"
#: One week back, in hours. The stub is a seasonal naive computed by *offset*,
#: which is the same forecast the timestamp-indexed baseline makes and a
#: completely different way of arriving at it.
SEASON_OFFSET = 168


def predict(history: pd.Series, target_times: pd.DatetimeIndex, cutoff: pd.Timestamp) -> pd.Series:
    values = history.to_numpy(dtype="float64")
    if len(values) < SEASON_OFFSET:
        raise ValueError(
            f"{NAME} needs at least {SEASON_OFFSET} hour(s) of context, got {len(values)}."
        )

    # `history` ends at cutoff - 1h, so the value one week before `cutoff + h`
    # sits at offset `SEASON_OFFSET - h` from the end. Positional arithmetic:
    # it is only correct because the guard already made the grid gapless.
    out = np.empty(len(target_times), dtype="float64")
    for i, target in enumerate(target_times):
        horizon = round((target - cutoff) / pd.Timedelta(hours=1))
        back = SEASON_OFFSET - horizon
        out[i] = values[-back] if 0 < back <= len(values) else values[-1]
    return pd.Series(out, index=target_times, name="prediction")


def make_arm(_series: pd.Series):
    """Factory for `foundation.guards.foresight_probe`.

    The stub holds no state, so the series is unused — and that is the point of
    the signature: an arm that *does* hold state must be rebuilt from whatever
    series the probe hands it, or the probe cannot see the leak.
    """
    return predict
