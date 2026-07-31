"""PSI and the two-sample Kolmogorov-Smirnov test, implemented here on purpose.

Both are three-line formulas wrapped in a lot of edge cases, and the edge cases
are where drift detectors quietly stop working: a bin with zero reference mass
makes PSI infinite, a constant column makes the quantile edges collapse, a
window of 30 rows makes every statistic significant. Importing them from a
library hides all of that behind a number nobody can defend in review.

So they are written out, every degenerate case is named and handled, and the
tests check the outputs against `scipy.stats.ks_2samp` (when scipy happens to be
installed — it is not a runtime dependency) and against values computed by hand.

Population Stability Index
--------------------------
    PSI = sum over bins of  (a_i - e_i) * ln(a_i / e_i)

with `e_i` the reference share of bin *i* and `a_i` the current share. Bin edges
come from the **reference** quantiles — the reference defines what "normal"
looks like, so it is the thing that gets to define the bins. The outermost
edges are pushed to +-inf so that current values outside the reference range
land in the extreme bins instead of being dropped.

Zero shares are floored at `EPSILON` rather than skipped: a bin that held 8% of
the reference and 0% of the current window is exactly the event PSI exists to
catch, and dropping it would report *less* drift the worse the drift got.

Kolmogorov-Smirnov
------------------
    D = sup_x |F_ref(x) - F_cur(x)|

computed exactly from the pooled order statistics. The p-value uses the
standard asymptotic form

    Q(lam) = 2 * sum_{k>=1} (-1)^(k-1) exp(-2 k^2 lam^2),
    lam    = (sqrt(n_e) + 0.12 + 0.11 / sqrt(n_e)) * D,
    n_e    = n1 * n2 / (n1 + n2)

which is accurate to ~1e-3 for the window sizes here (thousands of rows) and,
unlike the exact combinatorial form, does not need scipy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt
import pandas as pd

#: Anything `pd.Series(...)` accepts: a Series, an ndarray, a list, a column.
#: Named rather than repeated so the public statistics functions all state the
#: same contract -- they take array-likes and clean them, they do not require a
#: particular container.
ArrayLike = npt.ArrayLike

# Floor for a bin share. 1e-6 is well below any share a window of >=200 rows can
# legitimately produce (the smallest non-zero share is 1/n), so it only ever
# replaces a true zero.
EPSILON = 1e-6


@dataclass(frozen=True)
class PSIResult:
    """PSI plus everything needed to explain it."""

    psi: float
    bins: int
    binning: str  # "quantile" | "categorical" | "degenerate"
    reference_n: int
    current_n: int
    detail: list[dict] = field(default_factory=list)

    def as_dict(self, with_detail: bool = True) -> dict:
        out = {
            "psi": round(self.psi, 6),
            "bins": self.bins,
            "binning": self.binning,
            "reference_n": self.reference_n,
            "current_n": self.current_n,
        }
        if with_detail:
            out["by_bin"] = self.detail
        return out


@dataclass(frozen=True)
class KSResult:
    """The KS statistic, its p-value, and the sample sizes behind them."""

    statistic: float
    p_value: float
    reference_n: int
    current_n: int

    def as_dict(self) -> dict:
        return {
            "statistic": round(self.statistic, 6),
            "p_value": round(self.p_value, 8),
            "reference_n": self.reference_n,
            "current_n": self.current_n,
        }


def _clean(values: ArrayLike) -> np.ndarray:
    """Finite float64 values only — NaN and +-inf are dropped, not imputed.

    Imputing would invent mass in a bin; dropping is the honest choice and the
    per-column `reference_n` / `current_n` in the artifact makes the drop
    visible.
    """
    array = np.asarray(pd.Series(values).to_numpy(), dtype="float64")
    finite: np.ndarray = array[np.isfinite(array)]
    return finite


def quantile_bin_edges(reference: np.ndarray, bins: int) -> np.ndarray:
    """Bin edges from the reference quantiles, open at both ends.

    Duplicate edges (a spike in the distribution puts several quantiles on the
    same value) are collapsed, so the returned array can describe fewer than
    `bins` bins. That is correct: a column with three distinct values does not
    have ten bins, and pretending otherwise manufactures empty ones.
    """
    probabilities = np.linspace(0.0, 1.0, bins + 1)
    edges = np.unique(np.quantile(reference, probabilities))
    if len(edges) < 2:
        return edges
    edges[0], edges[-1] = -np.inf, np.inf
    return edges


def population_stability_index(
    reference: ArrayLike,
    current: ArrayLike,
    bins: int = 10,
    max_categorical_levels: int = 24,
) -> PSIResult:
    """PSI of `current` against `reference`.

    A column whose reference has at most `max_categorical_levels` distinct
    values is treated as categorical — one bin per level, plus a catch-all for
    levels that appear only in the current window. Quantile binning of
    `hour` or `dayofweek` would merge levels arbitrarily and hide exactly the
    kind of shift (a new weekly shape) that matters most.
    """
    ref, cur = _clean(reference), _clean(current)
    if len(ref) == 0 or len(cur) == 0:
        return PSIResult(0.0, 0, "degenerate", len(ref), len(cur))

    levels = np.unique(ref)
    if len(levels) <= max_categorical_levels:
        return _categorical_psi(ref, cur, levels)

    edges = quantile_bin_edges(ref, bins)
    if len(edges) < 2:  # a constant column: no drift is measurable
        return PSIResult(0.0, 1, "degenerate", len(ref), len(cur))

    ref_counts, _ = np.histogram(ref, bins=edges)
    cur_counts, _ = np.histogram(cur, bins=edges)
    labels = [f"[{_fmt(edges[i])}, {_fmt(edges[i + 1])})" for i in range(len(edges) - 1)]
    return _psi_from_counts(ref_counts, cur_counts, labels, "quantile", len(ref), len(cur))


def _categorical_psi(ref: np.ndarray, cur: np.ndarray, levels: np.ndarray) -> PSIResult:
    """One bin per reference level, plus `<unseen>` for new current values."""
    ref_counts = np.array([(ref == level).sum() for level in levels], dtype="float64")
    cur_counts = np.array([(cur == level).sum() for level in levels], dtype="float64")

    unseen = int(len(cur) - cur_counts.sum())
    labels = [_fmt(level) for level in levels]
    if unseen:
        ref_counts = np.append(ref_counts, 0.0)
        cur_counts = np.append(cur_counts, float(unseen))
        labels.append("<unseen>")

    return _psi_from_counts(ref_counts, cur_counts, labels, "categorical", len(ref), len(cur))


def _psi_from_counts(
    ref_counts: np.ndarray,
    cur_counts: np.ndarray,
    labels: list[str],
    binning: str,
    reference_n: int,
    current_n: int,
) -> PSIResult:
    ref_counts = np.asarray(ref_counts, dtype="float64")
    cur_counts = np.asarray(cur_counts, dtype="float64")

    expected = np.maximum(ref_counts / max(ref_counts.sum(), 1.0), EPSILON)
    actual = np.maximum(cur_counts / max(cur_counts.sum(), 1.0), EPSILON)
    contributions = (actual - expected) * np.log(actual / expected)

    detail = [
        {
            "bin": label,
            "reference_share": round(float(e), 6),
            "current_share": round(float(a), 6),
            "contribution": round(float(c), 6),
        }
        for label, e, a, c in zip(labels, expected, actual, contributions, strict=True)
    ]
    return PSIResult(
        psi=float(contributions.sum()),
        bins=len(labels),
        binning=binning,
        reference_n=reference_n,
        current_n=current_n,
        detail=detail,
    )


def _fmt(value: float) -> str:
    if value == -np.inf:
        return "-inf"
    if value == np.inf:
        return "+inf"
    return f"{value:.4g}"


def ks_two_sample(reference: ArrayLike, current: ArrayLike) -> KSResult:
    """Two-sample KS statistic and its asymptotic p-value.

    `D` is exact: the two ECDFs only change value at observed points, so
    evaluating them on the pooled sample and taking the largest gap is the
    supremum, not an approximation of it.
    """
    ref, cur = _clean(reference), _clean(current)
    n1, n2 = len(ref), len(cur)
    if n1 == 0 or n2 == 0:
        return KSResult(0.0, 1.0, n1, n2)

    ref.sort()
    cur.sort()
    pooled = np.concatenate([ref, cur])
    pooled.sort(kind="mergesort")

    # `side="right"` makes this F(x) = P(X <= x), the right-continuous ECDF.
    cdf_ref = np.searchsorted(ref, pooled, side="right") / n1
    cdf_cur = np.searchsorted(cur, pooled, side="right") / n2
    statistic = float(np.max(np.abs(cdf_ref - cdf_cur)))

    return KSResult(statistic, ks_p_value(statistic, n1, n2), n1, n2)


def ks_p_value(statistic: float, n1: int, n2: int, terms: int = 100) -> float:
    """P(D >= statistic) under the null, via the Kolmogorov distribution."""
    if statistic <= 0.0 or n1 == 0 or n2 == 0:
        return 1.0

    effective_n = math.sqrt(n1 * n2 / (n1 + n2))
    lam = (effective_n + 0.12 + 0.11 / effective_n) * statistic

    total = 0.0
    for k in range(1, terms + 1):
        term = 2.0 * (-1.0) ** (k - 1) * math.exp(-2.0 * (k**2) * (lam**2))
        total += term
        if abs(term) < 1e-12:  # the alternating series has converged
            break
    return float(min(max(total, 0.0), 1.0))


def summarise(reference: ArrayLike, current: ArrayLike) -> dict:
    """Location/scale summary of both windows — context for a PSI number.

    A PSI of 0.4 means nothing on its own; "the mean moved from 95 GW to 112 GW"
    is what a human acts on, so both go in the artifact.
    """
    ref, cur = _clean(reference), _clean(current)

    def block(values: np.ndarray) -> dict:
        if len(values) == 0:
            return {"n": 0, "mean": None, "std": None, "p05": None, "p50": None, "p95": None}
        return {
            "n": len(values),
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values, ddof=1)) if len(values) > 1 else 0.0, 4),
            "p05": round(float(np.percentile(values, 5)), 4),
            "p50": round(float(np.percentile(values, 50)), 4),
            "p95": round(float(np.percentile(values, 95)), 4),
        }

    ref_block, cur_block = block(ref), block(cur)
    shift = None
    if ref_block["mean"] is not None and cur_block["mean"] is not None:
        shift = round(cur_block["mean"] - ref_block["mean"], 4)

    return {"reference": ref_block, "current": cur_block, "mean_shift": shift}
