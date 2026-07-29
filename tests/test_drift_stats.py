"""The hand-rolled statistics have to be right, so they are checked three ways.

1. against values that can be worked out on paper (a two-bin PSI, an ECDF gap);
2. against `scipy.stats.ks_2samp` when scipy happens to be importable — it is
   not a runtime dependency, so the check skips rather than fails;
3. against the properties the formulas must have (symmetry, zero on identical
   samples, monotone in the size of the shift).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from drift import stats


def test_psi_is_zero_for_identical_samples():
    rng = np.random.default_rng(1)
    sample = rng.normal(100.0, 15.0, 4000)
    assert stats.population_stability_index(sample, sample).psi == pytest.approx(0.0, abs=1e-9)


def test_psi_two_bin_case_matches_the_formula_by_hand():
    """A 50/50 reference against a 25/75 current has a PSI we can write out."""
    reference = np.array([0.0] * 500 + [1.0] * 500)
    current = np.array([0.0] * 250 + [1.0] * 750)

    # Two levels -> categorical binning, shares 0.5/0.5 vs 0.25/0.75.
    expected = (0.25 - 0.5) * math.log(0.25 / 0.5) + (0.75 - 0.5) * math.log(0.75 / 0.5)

    result = stats.population_stability_index(reference, current)
    assert result.binning == "categorical"
    assert result.psi == pytest.approx(expected, rel=1e-9)


def test_psi_grows_with_the_size_of_the_shift():
    rng = np.random.default_rng(2)
    reference = rng.normal(0.0, 1.0, 5000)
    psis = [
        stats.population_stability_index(reference, rng.normal(shift, 1.0, 5000)).psi
        for shift in (0.0, 0.25, 0.5, 1.0, 2.0)
    ]
    assert psis == sorted(psis)
    assert psis[0] < 0.01  # no shift -> essentially zero
    assert psis[-1] > 1.0  # two sigma -> unmistakable


def test_psi_survives_a_current_bin_with_zero_mass():
    """The worst-case bin must inflate PSI, not divide by zero or vanish."""
    reference = np.concatenate([np.linspace(0, 10, 1000), np.linspace(90, 100, 1000)])
    current = np.linspace(0, 10, 2000)  # the entire upper mode disappeared

    result = stats.population_stability_index(reference, current)
    assert math.isfinite(result.psi)
    assert result.psi > 1.0


def test_psi_on_a_constant_column_is_degenerate_not_an_error():
    constant = np.full(1000, 7.0)
    result = stats.population_stability_index(constant, constant)
    assert result.psi == 0.0
    assert result.binning in {"degenerate", "categorical"}


def test_psi_bins_categoricals_by_level_not_by_quantile():
    rng = np.random.default_rng(3)
    reference = rng.integers(0, 24, 3000).astype(float)
    current = rng.integers(0, 24, 3000).astype(float)
    result = stats.population_stability_index(reference, current, max_categorical_levels=24)
    assert result.binning == "categorical"
    assert result.bins == 24


def test_psi_flags_a_level_never_seen_in_the_reference():
    reference = np.array([0.0, 1.0, 2.0] * 400)
    current = np.array([0.0, 1.0, 2.0, 99.0] * 300)
    result = stats.population_stability_index(reference, current)
    assert any(row["bin"] == "<unseen>" for row in result.detail)
    assert result.psi > 0.0


def test_ks_statistic_of_a_known_ecdf_gap():
    """Two ramps offset by half their range: the largest ECDF gap is 0.5."""
    reference = np.linspace(0.0, 1.0, 1001)
    current = np.linspace(0.5, 1.5, 1001)
    assert stats.ks_two_sample(reference, current).statistic == pytest.approx(0.5, abs=1e-3)


def test_ks_is_symmetric_and_zero_on_identical_samples():
    rng = np.random.default_rng(4)
    a, b = rng.normal(0, 1, 2000), rng.normal(0.4, 1, 2000)
    assert stats.ks_two_sample(a, a).statistic == 0.0
    assert stats.ks_two_sample(a, b).statistic == pytest.approx(stats.ks_two_sample(b, a).statistic)


def test_ks_p_value_rejects_a_real_shift_and_keeps_a_null():
    rng = np.random.default_rng(5)
    reference = rng.normal(0.0, 1.0, 3000)
    assert stats.ks_two_sample(reference, rng.normal(0.0, 1.0, 3000)).p_value > 0.05
    assert stats.ks_two_sample(reference, rng.normal(0.5, 1.0, 3000)).p_value < 1e-6


def test_ks_matches_scipy_when_scipy_is_available():
    """scipy is not a runtime dependency; when it is present, it is the oracle."""
    scipy_stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(6)

    for shift in (0.0, 0.15, 0.6):
        reference = rng.normal(0.0, 1.0, 1500)
        current = rng.normal(shift, 1.2, 1700)

        ours = stats.ks_two_sample(reference, current)
        theirs = scipy_stats.ks_2samp(reference, current, method="asymp")

        # D is computed exactly, so it must match to floating-point noise.
        assert ours.statistic == pytest.approx(float(theirs.statistic), abs=1e-12)
        # The p-value uses the standard asymptotic correction; 1e-3 absolute is
        # the documented accuracy of that approximation.
        assert ours.p_value == pytest.approx(float(theirs.pvalue), abs=1e-3)


def test_nan_and_inf_are_dropped_not_imputed():
    values = np.array([1.0, 2.0, np.nan, np.inf, -np.inf, 3.0])
    result = stats.ks_two_sample(values, values)
    assert result.reference_n == 3


def test_summarise_reports_the_mean_shift_in_data_units():
    summary = stats.summarise(np.full(500, 100.0), np.full(500, 112.5))
    assert summary["mean_shift"] == pytest.approx(12.5)
    assert summary["reference"]["n"] == 500
