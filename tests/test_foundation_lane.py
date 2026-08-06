"""The foundation lane's contract, proved without a foundation model.

No test here loads a checkpoint. The smallest usable one is 34,622,352 bytes,
6.6x the repository ceiling, and the `test` job touches no network — so what CI
can establish is that the seam, the guards and the isolation hold. The number
comes from the dispatch run and from nowhere else.

Every gate below was seen green on the defect it exists to catch before it was
written this way, and every one has a negative control. A gate that fires on the
honest case is not a gate; a gate that cannot fire at all is decoration.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from features import panel as panel_mod
from foundation import guards, stub, tsfm
from models import backtest, baseline, fixtures

REPO = Path(__file__).resolve().parents[1]
HOUR = pd.Timedelta(hours=1)


@pytest.fixture(scope="module")
def series() -> pd.Series:
    frame = fixtures.synthetic_series(days=90)
    panel = panel_mod.build_panel(
        frame["demand_mwh"], frame["temperature_c"], fixtures.synthetic_forecast(frame)
    )
    return panel[panel_mod.DEMAND_COLUMN].dropna().sort_index()


@pytest.fixture(scope="module")
def cutoffs(series: pd.Series) -> list[pd.Timestamp]:
    return backtest.make_cutoffs(series.index, 1, backtest.DEFAULT_HORIZONS, 12, 168)


# --------------------------------------------------------------------------
# G5 — isolation. Three conditions, and only the third has a reachable red
# state: the first two are true of a repository with no lane in it at all.
# --------------------------------------------------------------------------


def test_torch_is_declared_only_in_the_foundation_extra():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    extras = project["optional-dependencies"]

    assert any("torch" in dep for dep in extras["foundation"])
    assert not any("torch" in dep for dep in project["dependencies"])
    assert not any("torch" in dep for dep in extras["dev"])


def test_the_ci_sync_line_never_requests_the_foundation_extra():
    """The sync line, not the file.

    Scanning the whole workflow for the string fails on the G5 step's own error
    message, which names the extra it is refusing — the same trap
    `tests/test_workflows.py` already documents in `run_commands(strip_comments=)`:
    a test hunting a dangerous string must not match the sentence warning against
    it.
    """
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    syncs = [line for line in workflow.splitlines() if "uv sync" in line]

    assert syncs, "ci.yml no longer syncs anything"
    for line in syncs:
        assert "--extra foundation" not in line, f"CI installs the lane extra: {line.strip()}"


def test_importing_the_adapter_does_not_import_torch():
    """The only condition of G5 that a torch-free repository could fail.

    Run in a subprocess: this process may have imported torch for some other
    reason, and then the assertion would pass or fail for reasons unrelated to
    the adapter.
    """
    code = "import foundation.tsfm, sys; print('torch' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", (
        "importing foundation.tsfm pulled torch into sys.modules; the CI job "
        "installs --extra dev only and would fail at collection"
    )


def test_the_foundation_extra_is_present_in_the_lockfile():
    """`--frozen` reads the project's view from `uv.lock`, not from `pyproject.toml`.

    An extra declared in `pyproject.toml` and absent from the lock does not exist
    as far as CI is concerned: `uv sync --extra foundation --frozen` answers
    `Extra 'foundation' is not defined in the project's optional-dependencies
    table` — pointing at the file where it *is* defined.
    """
    lock = (REPO / "uv.lock").read_text(encoding="utf-8")
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    for dep in project["optional-dependencies"]["foundation"]:
        name = dep.split(">")[0].split("=")[0].split("[")[0].strip()
        assert f'name = "{name}"' in lock, f"{name} is in the extra but not in uv.lock"


# --------------------------------------------------------------------------
# Phase 0 — the licence gate, and the contamination fields it has to fill.
# --------------------------------------------------------------------------

CEILING_BYTES = 5_242_880


def test_no_usable_checkpoint_fits_under_the_size_ceiling():
    """The arithmetic that makes "vendor the weights" not a choice.

    Reproduced against the Hugging Face API on 2026-08-06: chronos-bolt-tiny is
    34,622,352 B, chronos-bolt-small 190,888,824 B, timesfm-2.0-500m
    1,995,406,976 B — 6.6x, 36.4x and 380.6x the ceiling.
    """
    assert tsfm.WEIGHTS["bytes"] > CEILING_BYTES
    assert tsfm.WEIGHTS["bytes"] / CEILING_BYTES > 36


def test_the_weights_are_pinned_by_revision_and_hash():
    """A tag can move; a revision and a content hash cannot.

    The sha256 is the LFS `X-Linked-ETag`, so it identifies the file that will be
    downloaded and was established without downloading 190 MB.
    """
    assert len(tsfm.WEIGHTS["revision"]) == 40
    assert len(tsfm.WEIGHTS["sha256"]) == 64
    assert tsfm.WEIGHTS["license"] == "apache-2.0"
    assert tsfm.WEIGHTS["gated"] is False


def test_the_contamination_fields_are_filled_for_the_checkpoint_that_runs():
    """The RFC's own evidence pointed at a model it had already cut.

    Its contamination risk cited the TimesFM card while cutting TimesFM from the
    lane, so the declared corpus described a checkpoint that would never run.
    These fields are about `DEFAULT_REPO`.
    """
    assert tsfm.WEIGHTS["repo"] == tsfm.DEFAULT_REPO
    assert tsfm.WEIGHTS["energy_domain_in_corpus"] in tsfm.ENERGY_DOMAIN_VALUES
    assert len(tsfm.WEIGHTS["pretraining_corpus_declared"]) > 80
    assert len(tsfm.WEIGHTS["energy_domain_evidence"]) > 80


def test_an_undeclared_corpus_still_carries_its_evidence():
    """`undeclared` must not become a shrug.

    It is the honest value here — the card enumerates nothing and the row-level
    pretraining split was not retrieved — but only if the reasoning travels with
    it. An `undeclared` with no evidence is indistinguishable from nobody having
    looked.
    """
    if tsfm.WEIGHTS["energy_domain_in_corpus"] != "undeclared":
        return
    evidence = tsfm.WEIGHTS["energy_domain_evidence"]
    assert "arXiv" in evidence, "no primary source behind the undeclared verdict"
    assert "not retrieved" in evidence, "the evidence must name what is still missing"


def test_the_lockfile_carries_no_cuda_wheels():
    """The lane assumes no GPU, and the lockfile has to agree.

    Resolving `torch` from PyPI pulled eighteen NVIDIA/CUDA packages —
    `nvidia-cudnn-cu13`, `cuda-toolkit`, `triton` and the rest — several
    gigabytes of wheels for hardware nobody in this lane is assumed to have.
    `[tool.uv.sources]` pins torch to the CPU index; this is what keeps it pinned.
    """
    cuda = [
        line
        for line in (REPO / "uv.lock").read_text(encoding="utf-8").splitlines()
        if line.startswith('name = "nvidia') or line.startswith('name = "cuda')
    ]
    assert cuda == [], f"CUDA wheels reached the lockfile: {cuda[:5]}"


# --------------------------------------------------------------------------
# G2 — contiguity. Runs once over the experiment series, before the arms fork.
# --------------------------------------------------------------------------


def test_contiguity_guard_is_silent_on_an_intact_series(series, cutoffs):
    repaired, report = guards.guard_contiguity(series, cutoffs)

    assert report["imputed_hours"] == 0
    pd.testing.assert_series_equal(repaired, series, check_freq=False)


def test_the_guard_never_touches_an_actual(series, cutoffs):
    """Imputing history is a repair; imputing an actual fabricates the answer.

    The first version returned only the repaired grid, which ends at
    `max(cutoffs) - 1h` — so every target hour vanished and `backtest.run` raised
    `Every fold was unscorable`. The fix is not to extend the grid over the
    actuals: a missing actual has to stay missing so the fold is dropped, which
    is the honest outcome and the one the harness already implements.
    """
    last_history_hour = max(cutoffs) - HOUR
    repaired, report = guards.guard_contiguity(series, cutoffs)

    assert report["actuals_untouched_from"] == last_history_hour.isoformat()
    after = series.index > last_history_hour
    pd.testing.assert_series_equal(
        repaired[repaired.index > last_history_hour], series[after], check_freq=False
    )
    # And the whole protocol still runs on what the guard handed back.
    result = backtest.run(repaired, stub.predict, cutoffs=cutoffs)
    assert len(result.folds) == len(cutoffs)


def test_contiguity_guard_refuses_a_hole_at_the_right_edge(series, cutoffs):
    """The canary the first design was green on.

    Reindexing to `history.index.max()` cannot see a gap that ends at the cutoff,
    which is the blackout still open when a day-ahead forecast is made.
    """
    target = cutoffs[len(cutoffs) // 2]
    holed = series.drop(index=pd.date_range(target - 6 * HOUR, periods=6, freq="h"))

    with pytest.raises(guards.LaneGateError) as excinfo:
        guards.guard_contiguity(holed, cutoffs)

    assert excinfo.value.gate == "contiguity"
    assert "cutoff-1h" in str(excinfo.value)


def test_contiguity_guard_refuses_a_long_interior_run(series, cutoffs):
    start = cutoffs[0] - 72 * HOUR
    holed = series.drop(index=pd.date_range(start, periods=guards.MAX_IMPUTED_RUN + 1, freq="h"))

    with pytest.raises(guards.LaneGateError, match="consecutive missing hour"):
        guards.guard_contiguity(holed, cutoffs)


def test_contiguity_guard_refuses_too_many_hours_in_total(series, cutoffs):
    """Scattered short gaps that add up. The budget is absolute, not a percentage.

    A relative budget means the same sentence authorises a different amount of
    fabricated demand on the fixture and on the real panel.
    """
    drops: list[pd.Timestamp] = []
    anchor = cutoffs[0] - 400 * HOUR
    for i in range(guards.MAX_IMPUTED_HOURS + 2):
        drops.append(anchor + i * 10 * HOUR)
    holed = series.drop(index=pd.DatetimeIndex(drops))

    with pytest.raises(guards.LaneGateError, match="MAX_IMPUTED_HOURS"):
        guards.guard_contiguity(holed, cutoffs)


def test_the_guard_hands_every_arm_the_same_series(series, cutoffs):
    """Why the guard runs before the arms fork, not inside the adapter.

    Inside the adapter, on the same missing hour the foundation model would get
    an interpolated number and the GBM would get NaN consumed natively — the arms
    would be scored on different data, which is what the fold contract forbids.
    """
    holed = series.drop(index=pd.DatetimeIndex([cutoffs[0] - 300 * HOUR]))
    repaired, report = guards.guard_contiguity(holed, cutoffs)

    assert report["imputed_hours"] == 1
    assert repaired.notna().all()
    assert (repaired.index.to_series().diff().dropna() == HOUR).all()


# --------------------------------------------------------------------------
# G3 — foresight. An invariance probe, per fold, with the arm rebuilt.
# --------------------------------------------------------------------------


def _oracle_factory(series: pd.Series):
    def make(built_on: pd.Series):
        return lambda history, targets, cutoff: built_on.reindex(targets)

    return make


def test_foresight_probe_is_silent_on_the_honest_stub(series, cutoffs):
    """Negative control, and the stub's own credential.

    A stub that could not pass its own negative control would make every positive
    result below meaningless.
    """
    report = guards.foresight_probe(stub.make_arm, series, cutoffs)

    assert report["clean"], report["caught"]
    assert report["probed"] == len(cutoffs)
    guards.assert_no_foresight("stub", report)


def test_foresight_probe_catches_perfect_foresight(series, cutoffs):
    report = guards.foresight_probe(_oracle_factory(series), series, cutoffs)

    assert len(report["caught"]) == len(cutoffs)
    with pytest.raises(guards.LaneGateError) as excinfo:
        guards.assert_no_foresight("oracle", report)
    assert excinfo.value.gate == "foresight"


def test_foresight_probe_catches_an_arm_that_only_cheats_on_some_folds(series, cutoffs):
    """The canary a tail-only probe cannot see.

    An arm reading the future everywhere except the last fold came out clean
    under a probe that perturbed only the tail — with an MAE 44x better than the
    seasonal naive and the gate green.
    """
    last = cutoffs[-1]

    def make(built_on: pd.Series):
        def predict(history, targets, cutoff):
            if cutoff == last:
                return baseline.predict(history, targets, cutoff)
            return built_on.reindex(targets)

        return predict

    report = guards.foresight_probe(make, series, cutoffs)

    assert len(report["caught"]) == len(cutoffs) - 1
    assert last.isoformat() not in report["caught"]


def test_the_probe_must_rebuild_the_arm_or_it_sees_nothing(series, cutoffs):
    """Why `make_arm` is a factory and not an arm.

    An arm closing over the original series is unaffected by perturbing a copy,
    so even perfect foresight scores clean. This pins the reason.
    """
    frozen_oracle = lambda history, targets, cutoff: series.reindex(targets)  # noqa: E731

    blind = guards.foresight_probe(lambda _s: frozen_oracle, series, cutoffs[:2])
    seeing = guards.foresight_probe(_oracle_factory(series), series, cutoffs[:2])

    assert blind["clean"], "a probe that does not rebuild the arm cannot see the leak"
    assert not seeing["clean"]


def test_the_perturbation_boundary_is_inclusive(series, cutoffs):
    """`>=`, not `>`. The character the design never specified.

    With `>` the target at exactly the cutoff stays intact, and an arm reading it
    goes unseen. Measured on this fixture: 36 perturbed hours versus 37, and the
    difference between catching a leaking arm and not.
    """
    cutoff = cutoffs[-1]
    shifted = series.copy()
    shifted[shifted.index >= cutoff] = shifted[shifted.index >= cutoff] * 1.5 + 5000.0

    assert shifted.loc[cutoff] != series.loc[cutoff], (
        "the hour stamped at the cutoff must be perturbed, or an arm reading it escapes"
    )


# --------------------------------------------------------------------------
# The stub: positional by design, because that is the property G2 protects.
# --------------------------------------------------------------------------


def test_the_stub_consumes_position_not_timestamps(series, cutoffs):
    """If the stub indexed by timestamp it would not exercise the contiguity guard.

    The hole has to fall inside the stub's reach. It reads offsets
    `SEASON_OFFSET - h` back from the end, i.e. the last 168 hours; a gap older
    than that shifts nothing and the test would pass for the wrong reason — which
    is how the first version of it failed.
    """
    cutoff = cutoffs[0]
    history = series[series.index < cutoff]
    targets = pd.DatetimeIndex([cutoff + i * HOUR for i in range(1, 25)])

    intact = stub.predict(history, targets, cutoff)
    holed = history.drop(index=history.index[-stub.SEASON_OFFSET // 2])
    shifted = stub.predict(holed, targets, cutoff)

    assert not np.allclose(intact.to_numpy(), shifted.to_numpy()), (
        "the stub read the same values after an hour was removed from its window, "
        "so it is not consuming position and the contiguity guard is untested by it"
    )


def test_the_stub_refuses_a_context_shorter_than_its_season(series, cutoffs):
    cutoff = cutoffs[0]
    history = series[series.index < cutoff].tail(stub.SEASON_OFFSET - 1)

    with pytest.raises(ValueError, match="needs at least 168 hour"):
        stub.predict(history, pd.DatetimeIndex([cutoff + HOUR]), cutoff)


def test_the_stub_runs_the_whole_protocol(series, cutoffs):
    result = backtest.run(series, stub.predict, cutoffs=cutoffs)

    assert len(result.folds) == len(cutoffs)
    assert result.overall["n"] == len(cutoffs) * 24
