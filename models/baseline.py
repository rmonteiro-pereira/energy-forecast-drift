"""Seasonal-naive baseline — the number every future model must beat.

For an hourly electricity series the strongest trivial predictor is *the same
hour, one week earlier*: it captures the daily shape and the weekday/weekend
split in one lag, which a 24 h naive cannot do.

    yhat(T) = y(T - 168h)

Because the backtest only ever asks for horizons of 1-24 h ahead of a fold
cutoff, the lag the baseline reads is always at least 144 h before that cutoff
— comfortably inside the information set. `predict` asserts this rather than
trusting it.
"""

from __future__ import annotations

import pandas as pd

SEASON_HOURS = 168  # one week
NAME = "seasonal_naive_168h"


class TemporalLeakageError(AssertionError):
    """Raised when a prediction would need data at or after the fold cutoff."""


def predict(
    history: pd.Series,
    target_times: pd.DatetimeIndex,
    cutoff: pd.Timestamp,
    season_hours: int = SEASON_HOURS,
) -> pd.Series:
    """Predict `target_times` from `history`, which must end before `cutoff`.

    Parameters
    ----------
    history:
        Hourly demand indexed by UTC timestamp. Callers pass the slice that was
        observable at `cutoff`; this function re-checks that invariant.
    target_times:
        Timestamps to forecast (all strictly after `cutoff`).
    cutoff:
        The fold boundary. Nothing at or after this instant may be read.
    """
    if len(history.index) and history.index.max() >= cutoff:
        raise TemporalLeakageError(
            f"history ends at {history.index.max()}, which is not strictly "
            f"before the fold cutoff {cutoff}"
        )

    lag = pd.Timedelta(hours=season_hours)
    source_times = target_times - lag

    if len(source_times) and source_times.max() >= cutoff:
        raise TemporalLeakageError(
            f"seasonal lag of {season_hours}h would read {source_times.max()}, "
            f"which is not strictly before the fold cutoff {cutoff}"
        )

    values = history.reindex(source_times).to_numpy()
    return pd.Series(values, index=target_times, name="prediction")
