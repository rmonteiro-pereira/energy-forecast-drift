"""Boundary tests written in response to a mutation-testing run.

The first `mutmut` pass over `drift/detectors.py` killed only 42% of mutants, and
the survivors clustered somewhere specific and alarming: **the threshold
comparisons themselves**. Mutating

    if mae_ratio >= thresholds.mae_degradation_alert:      # -> `>`
    elif share >= thresholds.drifted_share_alert:          # -> `>`
    ks_significant = ks.p_value < thresholds.ks_p_alert    # -> `<=`

left the whole suite green. Every existing test drove those comparisons from
well inside one region or the other, so the *boundary* — the one input where
`>=` and `>` disagree — was never exercised. A detector whose alert threshold is
off by one comparison is exactly the kind of monitor that looks fine for months
and then does not fire.

These tests pin each documented threshold at three points: just below, exactly
on, and just above. "Exactly on" is the assertion that matters; the neighbours
are there so a future threshold change fails loudly rather than silently sliding
the boundary.

Fixtures are constructed rather than fitted: `performance_drift` and
`_section_from_columns` are pure functions of numbers, so building the numbers
directly is faster, deterministic, and makes the boundary explicit in the test
instead of hidden inside a booster.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from drift import detectors
from drift.config import (
    DEFAULT_CURRENT_DAYS,
    DEFAULT_REFERENCE_DAYS,
    DEFAULT_THRESHOLDS,
    Severity,
)
from drift.windows import (
    ABS_ERROR_COLUMN,
    ABS_PCT_ERROR_COLUMN,
    ERROR_COLUMN,
    ScoredWindows,
)
from features import build as build_mod

T = DEFAULT_THRESHOLDS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _window(mae: float, mape: float, rows: int = 240, start: str = "2026-01-01") -> pd.DataFrame:
    """A scored window whose MAE is exactly `mae` and MAPE exactly `mape`.

    Errors alternate sign so the mean absolute error is `mae` while the bias is
    zero -- keeping bias out of the way of what these tests are pinning.
    """
    target = pd.date_range(start, periods=rows, freq="h", tz="UTC")
    sign = np.where(np.arange(rows) % 2 == 0, 1.0, -1.0)
    return pd.DataFrame(
        {
            "target_utc": target,
            ERROR_COLUMN: sign * mae,
            ABS_ERROR_COLUMN: np.full(rows, mae, dtype="float64"),
            ABS_PCT_ERROR_COLUMN: np.full(rows, mape, dtype="float64"),
        }
    )


def _windows(ref_mae: float, cur_mae: float, ref_mape: float, cur_mape: float) -> ScoredWindows:
    return ScoredWindows(
        reference=_window(ref_mae, ref_mape, start="2026-01-01"),
        current=_window(cur_mae, cur_mape, start="2026-02-01"),
        booster=None,
        split={},
        train_rows=0,
    )


def _severity_for_mae_ratio(ratio: float) -> Severity:
    """Run `performance_drift` with MAPE held flat and MAE degraded by `ratio`."""
    base = 1000.0
    section = detectors.performance_drift(
        _windows(ref_mae=base, cur_mae=base * (1.0 + ratio), ref_mape=2.0, cur_mape=2.0),
        T,
    )
    return section.severity


def _severity_for_mape_delta(delta_pp: float) -> Severity:
    """Run `performance_drift` with MAE held flat and MAPE moved by `delta_pp`."""
    return detectors.performance_drift(
        _windows(ref_mae=1000.0, cur_mae=1000.0, ref_mape=2.0, cur_mape=2.0 + delta_pp),
        T,
    ).severity


# ---------------------------------------------------------------------------
# performance drift -- the MAE degradation ladder
# ---------------------------------------------------------------------------
def test_mae_degradation_is_ok_just_below_the_warn_threshold():
    assert _severity_for_mae_ratio(T.mae_degradation_warn - 0.01) is Severity.OK


def test_mae_degradation_warns_exactly_at_a_representable_warn_threshold():
    """`>=`, not `>` -- pinned on a threshold float arithmetic can hit exactly.

    The *default* warn threshold cannot be tested this way, and that is a real
    property rather than a shortcoming of the test. `mae_ratio` is computed as
    `current / reference - 1.0`, and for the default 0.15 the nearest double is
    below the threshold: `1150.0 / 1000.0 - 1.0 == 0.14999999999999991`. So on
    the default configuration "exactly at the threshold" is not a state the
    production code can actually be in.

    0.25 *is* exactly representable (`1.25 - 1.0 == 0.25`), so it pins the
    comparison itself, which is the thing under test.
    """
    assert (1250.0 / 1000.0 - 1.0) == 0.25, "picked a non-representable boundary"

    bands = dataclasses.replace(T, mae_degradation_warn=0.25, mae_degradation_alert=0.75)
    section = detectors.performance_drift(
        _windows(ref_mae=1000.0, cur_mae=1250.0, ref_mape=2.0, cur_mape=2.0), bands
    )
    assert section.severity is Severity.WARN


def test_mae_degradation_alerts_exactly_at_a_representable_alert_threshold():
    assert (1750.0 / 1000.0 - 1.0) == 0.75

    bands = dataclasses.replace(T, mae_degradation_warn=0.25, mae_degradation_alert=0.75)
    section = detectors.performance_drift(
        _windows(ref_mae=1000.0, cur_mae=1750.0, ref_mape=2.0, cur_mape=2.0), bands
    )
    assert section.severity is Severity.ALERT


def test_mae_degradation_crosses_warn_and_alert_in_the_right_order():
    assert _severity_for_mae_ratio(T.mae_degradation_warn + 0.01) is Severity.WARN
    assert _severity_for_mae_ratio(T.mae_degradation_alert - 0.01) is Severity.WARN
    assert _severity_for_mae_ratio(T.mae_degradation_alert + 0.01) is Severity.ALERT


def test_mae_degradation_alerts_above_the_alert_threshold():
    assert _severity_for_mae_ratio(T.mae_degradation_alert + 0.25) is Severity.ALERT


def test_an_improving_model_never_alerts():
    """Negative degradation is the model getting better; it must stay `ok`."""
    assert _severity_for_mae_ratio(-0.50) is Severity.OK


# ---------------------------------------------------------------------------
# performance drift -- the MAPE ladder, which is a separate comparison
# ---------------------------------------------------------------------------
def test_mape_degradation_is_ok_just_below_the_warn_threshold():
    assert _severity_for_mape_delta(T.mape_degradation_warn_pp - 0.01) is Severity.OK


def test_mape_degradation_warns_exactly_at_the_warn_threshold():
    """MAPE is a subtraction, not a ratio, so the default threshold *is* exact.

    `2.5 - 2.0 == 0.5` holds in binary floating point, so unlike the MAE ladder
    this boundary is reachable on the shipped configuration.
    """
    assert T.mape_degradation_warn_pp == (2.5 - 2.0)
    assert _severity_for_mape_delta(T.mape_degradation_warn_pp) is Severity.WARN


def test_mape_degradation_alerts_exactly_at_the_alert_threshold():
    assert T.mape_degradation_alert_pp == (3.0 - 2.0)
    assert _severity_for_mape_delta(T.mape_degradation_alert_pp) is Severity.ALERT


def test_mae_and_mape_take_the_worse_of_the_two():
    """The section severity is the worst signal, not the last one evaluated."""
    section = detectors.performance_drift(
        _windows(
            ref_mae=1000.0,
            cur_mae=1000.0 * (1.0 + T.mae_degradation_alert),  # ALERT
            ref_mape=2.0,
            cur_mape=2.0,  # OK
        ),
        T,
    )
    assert section.severity is Severity.ALERT


def test_performance_drift_reports_insufficient_data_rather_than_dividing_by_zero():
    empty = _window(1000.0, 2.0, rows=0)
    section = detectors.performance_drift(
        ScoredWindows(
            reference=empty, current=_window(1000.0, 2.0), booster=None, split={}, train_rows=0
        ),
        T,
    )
    assert section.severity is Severity.OK
    assert section.details["status"] == detectors.INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# section rollup -- the drifted-share ladder
# ---------------------------------------------------------------------------
def _column(name: str, psi: float, n: int = 1000) -> dict:
    """A `compare_column`-shaped dict at a chosen PSI, without running the stats."""
    severity = T.psi_severity(psi)
    return {
        "column": name,
        "deterministic": False,
        "insufficient_data": n < T.min_samples,
        "severity": severity.value,
        "psi": {"psi": psi, "bins": 10, "binning": "quantile", "reference_n": n, "current_n": n},
        "ks": {
            "statistic": 0.0,
            "p_value": 1.0,
            "reference_n": n,
            "current_n": n,
            "significant": False,
        },
        "distribution": {"mean_shift": 0.0},
        "drift_detected": severity is not Severity.OK,
    }


def _share_severity(n_alerting: int, n_total: int) -> Severity:
    """Rollup severity when `n_alerting` of `n_total` columns are above alert PSI."""
    columns = [
        _column(f"f{i}", T.psi_alert + 0.5 if i < n_alerting else 0.0) for i in range(n_total)
    ]
    severity, _rollup = detectors._section_from_columns("feature", columns, T)
    return severity


def test_a_single_scored_column_reports_its_own_severity():
    """With one column, `share` is 0 or 1 and the share ladder is meaningless."""
    assert _share_severity(n_alerting=1, n_total=1) is Severity.ALERT
    assert _share_severity(n_alerting=0, n_total=1) is Severity.OK


def test_drifted_share_alerts_exactly_at_the_alert_share():
    """20 columns, 6 alerting = 0.30 = exactly `drifted_share_alert`."""
    n_total = 20
    exactly = round(T.drifted_share_alert * n_total)
    assert exactly / n_total == pytest.approx(T.drifted_share_alert)
    assert _share_severity(n_alerting=exactly, n_total=n_total) is Severity.ALERT


def test_drifted_share_below_the_alert_share_only_warns():
    n_total = 20
    below = round(T.drifted_share_alert * n_total) - 1
    assert _share_severity(n_alerting=below, n_total=n_total) is Severity.WARN


def test_no_drifted_columns_is_ok():
    assert _share_severity(n_alerting=0, n_total=20) is Severity.OK


def test_a_single_alerting_column_warns_even_when_its_share_is_below_the_warn_share():
    """Isolates the `alerting` disjunct in `alerting or share >= warn or warning`.

    One alerting column in twenty is a share of 0.05, below the 0.15 warn share,
    and there are no warning columns -- so `alerting` is the only disjunct that
    can carry the branch. Every other test drives a share large enough that the
    middle disjunct is true as well, which masks a mutation turning the `or`
    into an `and`.
    """
    assert T.drifted_share_warn > 1 / 20, "fixture no longer isolates the disjunct"
    assert T.drifted_share_alert > 1 / 20

    assert _share_severity(n_alerting=1, n_total=20) is Severity.WARN


def test_the_warn_share_comparison_is_inclusive():
    """`share >= warn`, not `>`.

    This one is only observable under a degenerate configuration, and that is
    worth stating plainly rather than hiding. `share` is `len(alerting) /
    len(scored)`, so whenever `alerting` is empty the share is exactly 0.0 --
    and whenever it is non-empty the first disjunct has already carried the
    branch. The single input where `>=` and `>` disagree is therefore a warn
    share of 0.0.

    Killing it there is still worth doing: the comparison should be inclusive
    for the same reason the alert share is, and a future refactor that reorders
    the disjuncts would make this reachable on ordinary settings.
    """
    bands = dataclasses.replace(T, drifted_share_warn=0.0)
    columns = [_column(f"f{i}", 0.0) for i in range(5)]

    severity, rollup = detectors._section_from_columns("feature", columns, bands)
    assert rollup["drifted_share"] == 0.0
    assert severity is Severity.WARN


def test_columns_below_the_minimum_sample_size_are_not_scored():
    """An under-powered column must not be able to raise the section severity."""
    columns = [_column("tiny", T.psi_alert + 5.0, n=T.min_samples - 1)]
    severity, rollup = detectors._section_from_columns("feature", columns, T)
    assert rollup["columns_scored"] == 0
    assert severity is Severity.OK


def test_deterministic_columns_are_reported_but_never_vote():
    """The calendar-column exclusion, pinned: PSI 7 on `month` must not alert."""
    month = _column("month", 7.0)
    month["deterministic"] = True
    severity, rollup = detectors._section_from_columns("feature", [month], T)
    assert severity is Severity.OK
    assert rollup["columns_scored"] == 0
    assert "month" in rollup["columns_excluded_deterministic"]


# ---------------------------------------------------------------------------
# compare_column -- the KS significance and min-sample comparisons
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("p_value", "expected"),
    [
        (T.ks_p_alert / 10.0, True),  # clearly significant
        (T.ks_p_alert * 10.0, False),  # clearly not
        # Exactly at alpha. `<` is strict, so this is *not* significant -- the
        # one input where `<` and `<=` disagree, and the reason a mutation to
        # `<=` survived a suite that only ever tested 10x either side.
        (T.ks_p_alert, False),
    ],
)
def test_ks_significance_follows_the_configured_alpha(p_value, expected, monkeypatch):
    """`p_value < alpha`, pinned on both sides of the configured alpha."""
    fake = type(
        "KS",
        (),
        {
            "statistic": 0.5,
            "p_value": p_value,
            "reference_n": 1000,
            "current_n": 1000,
            "as_dict": lambda self: {
                "statistic": 0.5,
                "p_value": p_value,
                "reference_n": 1000,
                "current_n": 1000,
            },
        },
    )()
    monkeypatch.setattr(detectors.stats, "ks_two_sample", lambda a, b: fake)

    reference = pd.Series(np.linspace(0.0, 100.0, 1000))
    current = pd.Series(np.linspace(0.0, 100.0, 1000))
    result = detectors.compare_column(reference, current, "x", T)
    assert result["ks"]["significant"] is expected


def test_psi_severity_ladder_is_inclusive_at_both_thresholds():
    """`psi_severity` is the single place the PSI bands are defined."""
    assert T.psi_severity(T.psi_warn - 1e-9) is Severity.OK
    assert T.psi_severity(T.psi_warn) is Severity.WARN
    assert T.psi_severity(T.psi_alert - 1e-9) is Severity.WARN
    assert T.psi_severity(T.psi_alert) is Severity.ALERT


def test_thresholds_can_be_tightened_and_the_ladder_follows():
    """The bands are configuration, not constants baked into the comparisons."""
    strict = dataclasses.replace(T, mae_degradation_warn=0.01, mae_degradation_alert=0.02)
    section = detectors.performance_drift(
        _windows(ref_mae=1000.0, cur_mae=1000.0 * 1.025, ref_mape=2.0, cur_mape=2.0),
        strict,
    )
    assert section.severity is Severity.ALERT


def test_a_column_with_exactly_the_minimum_sample_size_is_scored():
    """`min(ref_n, cur_n) < min_samples`, not `<=`.

    At exactly `min_samples` the column has the power it was asked for, so it
    must count. Marking it insufficient forces the severity to OK and silently
    removes the column from the section vote -- a monitor that stops looking at
    precisely the sample size it was configured to require.
    """
    n = 50
    bands = dataclasses.replace(T, min_samples=n)
    rng = np.random.default_rng(3)
    reference = pd.Series(rng.normal(100.0, 5.0, n))
    current = pd.Series(rng.normal(140.0, 5.0, n))

    result = detectors.compare_column(reference, current, "x", bands)

    assert result["psi"]["reference_n"] == n
    assert result["insufficient_data"] is False, (
        "a column with exactly min_samples rows must be scored, not excluded"
    )
    assert result["severity"] != Severity.OK.value, (
        "the fixture is meant to drift; if it does not, the test proves nothing"
    )


# ---------------------------------------------------------------------------
# feature_drift -- the "nothing was eligible" branch, through the real detector
# ---------------------------------------------------------------------------
def _feature_frame(rows: int, start: str, *, level: float = 100.0) -> pd.DataFrame:
    """A frame carrying every model input, so `feature_drift` can run on it."""
    rng = np.random.default_rng(abs(hash(start)) % 2**32)
    frame = pd.DataFrame({"target_utc": pd.date_range(start, periods=rows, freq="h", tz="UTC")})
    for name in build_mod.FEATURE_COLUMNS:
        frame[name] = rng.normal(level, 5.0, rows)
    return frame


def test_feature_drift_reports_the_insufficient_summary_when_nothing_is_eligible():
    """The branch was only ever reached by calling `_section_from_columns` directly.

    Going through `feature_drift` is the difference that matters: the summary
    string this branch produces is what a human reads in the artifact, and it
    was never asserted, so a mutation blanking it to `None` survived.
    """
    windows = ScoredWindows(
        reference=_feature_frame(10, "2026-01-01"),
        current=_feature_frame(10, "2026-02-01"),
        booster=None,
        split={},
        train_rows=0,
    )
    section = detectors.feature_drift(windows, T)

    assert section.severity is Severity.OK
    assert section.summary == "not enough rows in one of the windows to score feature drift"
    assert section.details["columns_scored"] == 0


def test_feature_drift_summary_names_the_worst_column_when_columns_are_scored():
    """The other side of the same branch, so neither can be taken unconditionally."""
    rows = T.min_samples + 50
    windows = ScoredWindows(
        reference=_feature_frame(rows, "2026-01-01", level=100.0),
        current=_feature_frame(rows, "2026-02-01", level=180.0),
        booster=None,
        split={},
        train_rows=0,
    )
    section = detectors.feature_drift(windows, T)

    assert section.details["columns_scored"] > 0
    assert "feature(s) above PSI" in section.summary
    assert section.details["max_psi_column"] in section.summary


def test_performance_drift_is_insufficient_when_only_the_current_window_is_empty():
    """Isolates the second disjunct of the three-way insufficient-data guard.

    The existing test empties the *reference* window, which makes the first and
    third disjuncts true together and masks the middle one. An empty current
    window with a healthy reference is the input where only `not current["n"]`
    can stop the division.
    """
    section = detectors.performance_drift(
        ScoredWindows(
            reference=_window(1000.0, 2.0),
            current=_window(1000.0, 2.0, rows=0),
            booster=None,
            split={},
            train_rows=0,
        ),
        T,
    )
    assert section.severity is Severity.OK
    assert section.details["status"] == detectors.INSUFFICIENT_DATA


def test_the_reference_and_current_windows_are_the_same_length():
    """PSI is not comparable across window sizes, so the two must match.

    `docs/DRIFT-EVALUATION.md` measured this rather than assumed it: matched
    fortnights a year apart, 0.30 °C apart in the mean, scored PSI 0.177 and
    warned; whole months a year apart, 0.04 °C apart, scored 0.074 and stayed
    quiet. The bins come from the reference, so a short window encodes where in
    the season it sits as much as it encodes the distribution.

    The shipped geometry was 28 days of reference against 14 of current, which
    put a fortnight and a month on one threshold scale. That page calls it "the
    actual bug and it is not a threshold question", so it gets an assertion
    rather than a paragraph.
    """
    assert DEFAULT_REFERENCE_DAYS == DEFAULT_CURRENT_DAYS, (
        f"reference is {DEFAULT_REFERENCE_DAYS} days and current is "
        f"{DEFAULT_CURRENT_DAYS}; PSI computed over reference quantile bins is "
        "not comparable between windows of different length, and the shorter one "
        "will score higher on identical data"
    )
