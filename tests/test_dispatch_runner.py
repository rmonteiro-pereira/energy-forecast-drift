"""The dispatch runner — the command Phase 6 named and did not have.

Every test here runs against `--tsfm stub`, which is what CI can execute: the
checkpoint is 36x the size ceiling and the `test` job touches no network. What
these prove is that the run refuses the things it must refuse and assembles the
things it must assemble. The number itself comes from the dispatch run against
the real panel and from nowhere else.

The refusals get more attention than the happy path on purpose. A runner that
produces an artifact is easy; a runner that declines to produce a *misleading*
one is the part that had to be built deliberately, and each refusal below was
seen firing before it was written down.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from foundation import __main__ as runner


@pytest.fixture
def pinned(monkeypatch):
    """One thread, declared in the environment as well as in the parameters."""
    monkeypatch.setenv("OMP_NUM_THREADS", "1")


# --------------------------------------------------------------------------
# The refusals.
# --------------------------------------------------------------------------


def test_a_run_whose_threads_are_not_pinned_does_not_start(monkeypatch):
    """`num_threads: 1` in the params is not the same statement as one thread.

    Measured: `params={"num_threads": 1}` alone gave a CPU:wall ratio of 1.38,
    which is impossible for a single thread — OpenMP keeps spinning. Only
    `OMP_NUM_THREADS` in the environment brings it to 0.99. A cost table
    published from the first configuration describes a machine nobody chose.
    """
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    with pytest.raises(runner.DispatchError, match="OMP_NUM_THREADS"):
        runner._assert_threads_are_pinned(1)


def test_threads_pinned_in_both_places_is_accepted(pinned):
    runner._assert_threads_are_pinned(1)


def test_an_unset_omp_is_a_refusal_not_a_default(monkeypatch):
    """Absent is not one. The failure is silent precisely when nobody set it."""
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    with pytest.raises(runner.DispatchError, match="OMP_NUM_THREADS"):
        runner._assert_threads_are_pinned(1)


def test_a_synthetic_artifact_is_refused_at_the_published_path():
    """`metrics/foundation.json` is real or absent, enforced before the write.

    `tests/test_lane_artifact.py` states the same rule, and it can only notice
    once the file is on disk. The person who would be misled by a fixture-derived
    artifact at the published path is the person who typed `--source synthetic`
    by accident, and they need the refusal now, not at review.
    """
    artifact = {"is_real": False, "data": {"kind": "synthetic_fixture"}}
    with pytest.raises(runner.DispatchError, match="real or absent"):
        runner.refuse_to_publish_a_fixture(runner.PUBLISHED, artifact)


def test_a_real_artifact_is_accepted_at_the_published_path():
    artifact = {"is_real": True, "data": {"kind": runner.PUBLISHABLE_KIND}}
    runner.refuse_to_publish_a_fixture(runner.PUBLISHED, artifact)


def test_is_real_alone_does_not_open_the_published_path():
    """Both halves, because either alone is satisfiable by a mislabelled run."""
    artifact = {"is_real": True, "data": {"kind": "synthetic_fixture"}}
    with pytest.raises(runner.DispatchError, match="real or absent"):
        runner.refuse_to_publish_a_fixture(runner.PUBLISHED, artifact)


def test_a_synthetic_artifact_may_be_written_anywhere_else(tmp_path):
    artifact = {"is_real": False, "data": {"kind": "synthetic_fixture"}}
    runner.refuse_to_publish_a_fixture(tmp_path / "foundation.json", artifact)


def test_an_unknown_arm_id_is_refused_by_name():
    with pytest.raises(runner.DispatchError, match="unknown arm id"):
        runner._resolve_arm_ids("lgbm_17_demand_only,lgbm_99_imaginary")


def test_an_empty_arm_list_is_refused_rather_than_producing_nothing():
    with pytest.raises(runner.DispatchError, match="vacuous"):
        runner._resolve_arm_ids(" , ")


def test_all_means_the_whole_ladder():
    from models import arms as arms_mod

    assert set(runner._resolve_arm_ids("all")) == set(arms_mod.ARMS)


# --------------------------------------------------------------------------
# The pieces the assembly depends on.
# --------------------------------------------------------------------------


def test_the_gbm_panel_carries_the_guarded_series_and_no_invented_weather():
    """An hour the guard fabricated has a demand value and no temperature.

    Interpolating the covariate to match the interpolated target would be the
    second fabrication hiding behind the first, and the GBM consumes NaN
    natively — there is nothing to gain by inventing it.
    """
    grid = pd.date_range("2026-01-01", periods=6, freq="h", name="timestamp_utc")
    fabricated = grid[3]
    # The panel is what arrived: hour 3 never did. The guard hands back the full
    # grid with that hour interpolated, so `_guarded_panel` has to *add* a row.
    observed = grid.delete(3)
    panel = pd.DataFrame(
        {"demand_mwh": [1.0, 2.0, 3.0, 5.0, 6.0], "temp_c": [10.0] * 5}, index=observed
    )
    guarded = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], index=grid, name="demand_mwh")

    out = runner._guarded_panel(panel, guarded)

    assert out.index.equals(grid), "the panel did not follow the guard onto the repaired grid"
    assert out["demand_mwh"].tolist() == guarded.tolist()
    assert pd.isna(out.loc[fabricated, "temp_c"]), "the fabricated hour was given a temperature"
    assert out["temp_c"].drop(index=fabricated).notna().all(), "an observed reading was lost"


def test_training_hours_counts_what_was_observable_at_the_fit():
    index = pd.date_range("2026-01-01", periods=10, freq="h", name="timestamp_utc")
    series = pd.Series(range(10), index=index, dtype="float64")

    assert runner._training_hours(series, index[4]) == 4
    assert runner._training_hours(series, index[0]) == 0


# --------------------------------------------------------------------------
# End to end, on the stub.
# --------------------------------------------------------------------------


def test_the_runner_produces_an_artifact_that_passes_its_own_gates(tmp_path, pinned):
    out = tmp_path / "foundation.json"
    code = runner.main(
        [
            "--source",
            "synthetic",
            "--fixture-days",
            "60",
            "--weeks",
            "1",
            "--arms",
            "lgbm_12_no_calendar",
            "--tsfm",
            "stub",
            "--probe-gbm-folds",
            "1",
            "--probe-tsfm-folds",
            "1",
            "--out",
            str(out),
        ]
    )

    assert code == 0
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert artifact["failed_gate"] is None
    assert artifact["is_real"] is False
    assert artifact["data"]["kind"] == "synthetic_fixture"
    assert {a["id"] for a in artifact["arms"]} == {"lgbm_12_no_calendar", "stub_zero_shot"}
    assert len({a["n"] for a in artifact["arms"]}) == 1, "the arms were scored on different folds"


def test_the_refit_arm_reports_a_refit_cost_the_zero_shot_arm_does_not(tmp_path, pinned):
    """The three cost lines exist to keep this difference visible.

    The refit is the GBM's whole cost and a zero-shot model refits never, so a
    runner that folded `fit` into `infer` would hand the foundation model a win
    that belongs to the protocol. The first lane artifact reported `refits: 13`
    beside `fit_cpu_s: 0.0`, which is that failure with the sign flipped: the
    GBM's cost had vanished instead of being shared.
    """
    out = tmp_path / "foundation.json"
    assert (
        runner.main(
            [
                "--source",
                "synthetic",
                "--fixture-days",
                "60",
                "--weeks",
                "1",
                "--arms",
                "lgbm_12_no_calendar",
                "--tsfm",
                "stub",
                "--probe-gbm-folds",
                "1",
                "--probe-tsfm-folds",
                "1",
                "--out",
                str(out),
            ]
        )
        == 0
    )

    arms = {a["id"]: a for a in json.loads(out.read_text(encoding="utf-8"))["arms"]}
    gbm, zero_shot = arms["lgbm_12_no_calendar"], arms["stub_zero_shot"]

    assert gbm["refits"] > 1 and gbm["fit_cpu_s"] > 0.0
    assert zero_shot["refits"] == 0 and zero_shot["fit_cpu_s"] == 0.0
    assert gbm["fit_cpu_s"] > gbm["infer_cpu_s"], "the refit stopped dominating; re-read the table"


def test_every_gate_that_ran_leaves_its_report_in_the_record(tmp_path, pinned):
    """G3 in particular: a gate that runs and records nothing cannot be audited.

    A reader of the artifact must be able to tell a probe that came back clean
    from a probe that never happened, and `clean: true` over zero folds is the
    shape of the second pretending to be the first — hence `probed` and
    `coverage` alongside it.
    """
    out = tmp_path / "foundation.json"
    runner.main(
        [
            "--source",
            "synthetic",
            "--fixture-days",
            "60",
            "--weeks",
            "1",
            "--arms",
            "lgbm_12_no_calendar",
            "--tsfm",
            "stub",
            "--probe-gbm-folds",
            "2",
            "--probe-tsfm-folds",
            "0",
            "--out",
            str(out),
        ]
    )
    artifact = json.loads(out.read_text(encoding="utf-8"))

    assert set(artifact["foresight"]) == {"lgbm_12_no_calendar", "stub_zero_shot"}
    for arm_id, report in artifact["foresight"].items():
        assert report["probed"] >= 1, f"{arm_id}: clean over zero folds is not clean"
        assert report["clean"] is True
        assert report["caught"] == []
    assert artifact["foresight"]["lgbm_12_no_calendar"]["probed"] == 2
    assert artifact["foresight"]["stub_zero_shot"]["coverage"] == "all"
