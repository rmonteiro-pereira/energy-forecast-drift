"""End-to-end: `python -m drift.run` must write four sections and a verdict.

This is the exit criterion for M4 expressed as a test, so a refactor that keeps
every unit passing but breaks the artifact shape still fails the build. It also
guards the honesty flag: an artifact produced from the fixture has to carry
`"is_real": false` and the synthetic warning, at the top level, every time.
"""

from __future__ import annotations

import json

import pytest

from drift import evidently_report
from drift import run as drift_run
from drift.config import Severity

# The full 200-day fixture with the default 300 boosting rounds takes ~40s;
# these flags keep the end-to-end path honest but quick.
FAST_ARGS = [
    "--source",
    "synthetic",
    "--train-stride-hours",
    "12",
    "--num-boost-round",
    "60",
    "--no-evidently",
]


@pytest.fixture(scope="module")
def artifact(tmp_path_factory) -> dict:
    out = tmp_path_factory.mktemp("drift") / "drift.json"
    assert drift_run.main([*FAST_ARGS, "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["_out_dir"] = str(out.parent)
    return payload


def test_the_artifact_has_all_four_drift_sections(artifact):
    assert set(artifact["drift"]) == {"feature", "target", "prediction", "performance"}
    for name, section in artifact["drift"].items():
        assert section["drift_type"] == name
        assert section["severity"] in {s.value for s in Severity}
        assert isinstance(section["drift_detected"], bool)
        assert section["summary"]


def test_the_artifact_has_a_structured_verdict(artifact):
    verdict = artifact["verdict"]
    assert isinstance(verdict["should_retrain"], bool)
    assert verdict["action"] in {"retrain", "watch", "none"}
    assert verdict["rule"].startswith("R")
    assert verdict["rationale"]
    assert set(verdict["signals"]) == set(artifact["drift"])


def test_the_artifact_carries_the_thresholds_that_produced_it(artifact):
    thresholds = artifact["thresholds"]
    assert thresholds["psi_alert"] == 0.20
    assert "mae_degradation_alert" in thresholds


def test_the_artifact_stays_honest_about_synthetic_data(artifact):
    assert artifact["is_real"] is False
    assert artifact["data"]["is_real"] is False
    assert "SYNTHETIC" in artifact["warning"]
    assert artifact["data"]["kind"] == "synthetic_fixture"


def test_the_window_split_is_recorded_in_the_artifact(artifact):
    windows = artifact["windows"]
    assert windows["rows"]["train"] > 0
    assert windows["rows"]["reference"] > 0
    assert windows["rows"]["current"] > 0
    assert windows["reference_start_utc"] < windows["current_start_utc"]


def test_a_markdown_summary_is_written_next_to_the_json(artifact):
    from pathlib import Path

    summary = Path(artifact["_out_dir"]) / "drift_summary.md"
    assert summary.exists()
    text = summary.read_text(encoding="utf-8")
    assert "SYNTHETIC" in text
    assert "Verdict" in text
    for name in ("feature", "target", "prediction", "performance"):
        assert name in text


def test_the_simulated_shift_flag_stamps_the_artifact_and_fires_the_alarm(tmp_path):
    """`--simulate-shift` must be impossible to mistake for an observed episode."""
    out = tmp_path / "drift_shift.json"
    assert drift_run.main([*FAST_ARGS, "--out", str(out), "--simulate-shift", "12000"]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    shift = payload["simulated_shift"]
    assert shift["demand_offset_mw"] == 12000.0
    assert "SIMULATED" in shift["warning"]
    assert payload["verdict"]["should_retrain"] is True

    summary = (tmp_path / "drift_summary.md").read_text(encoding="utf-8")
    assert "SIMULATED DRIFT EPISODE" in summary


def test_fail_on_retrain_turns_the_verdict_into_an_exit_code(tmp_path):
    out = tmp_path / "gate.json"
    code = drift_run.main(
        [*FAST_ARGS, "--out", str(out), "--simulate-shift", "12000", "--fail-on-retrain"]
    )
    assert code == 1, "a retrain verdict must be able to fail a CI gate"


def test_a_clean_run_passes_the_same_gate(tmp_path):
    out = tmp_path / "clean.json"
    assert drift_run.main([*FAST_ARGS, "--out", str(out), "--fail-on-retrain"]) == 0


def test_evidently_is_optional_and_records_why_it_is_absent(monkeypatch):
    """The daily pipeline must not fail because an optional dependency is gone."""
    monkeypatch.setattr(evidently_report, "is_available", lambda: False)
    report = evidently_report.build_report(windows=None)
    assert report["status"] == evidently_report.UNAVAILABLE
    assert "optional" in report["reason"]


@pytest.mark.skipif(not evidently_report.is_available(), reason="evidently not installed")
def test_evidently_gives_a_second_opinion_when_installed(tmp_path):
    out = tmp_path / "with_evidently.json"
    args = [a for a in FAST_ARGS if a != "--no-evidently"]
    assert drift_run.main([*args, "--out", str(out), "--no-html"]) == 0

    evidently = json.loads(out.read_text(encoding="utf-8"))["evidently"]
    assert evidently["status"] == evidently_report.OK
    assert evidently["columns"], "the second opinion must name the columns it scored"
    assert evidently["drifted_share"] is not None
