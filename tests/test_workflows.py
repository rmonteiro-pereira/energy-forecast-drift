"""The workflow YAMLs are code, so they get tested like code.

A broken workflow is normally discovered by pushing a commit and watching a red
tick, which is a slow feedback loop for a repo that has no remote yet. Parsing
both files here catches a syntax error immediately, and the rest of the
assertions pin down the properties that make the daily cron safe to leave
scheduled: it stays inert until someone activates it, it refuses to run without
a key, and it stages explicit paths only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
DAILY = WORKFLOWS / "daily.yml"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def steps_of(workflow: dict, job: str) -> list[dict]:
    return workflow["jobs"][job]["steps"]


def run_commands(workflow: dict, job: str, strip_comments: bool = False) -> str:
    """Every `run:` block of a job, concatenated.

    `strip_comments` drops shell comment lines — the workflow explains itself
    inline, and a test looking for a dangerous command must not match the
    sentence warning against it.
    """
    text = "\n".join(step.get("run", "") for step in steps_of(workflow, job))
    if not strip_comments:
        return text
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


@pytest.mark.parametrize("path", [CI, DAILY], ids=["ci", "daily"])
def test_the_workflow_parses(path):
    workflow = load(path)
    assert workflow["name"]
    assert workflow["jobs"], "a workflow with no jobs would silently do nothing"


# ---------------------------------------------------------------------------
# daily.yml — the live cron
# ---------------------------------------------------------------------------
def test_the_daily_cron_is_still_inert():
    """It must not start firing the moment the repo is pushed.

    `on:` parses to the boolean `True` in YAML 1.1 — that is not a bug here,
    just PyYAML being faithful to the spec.
    """
    triggers = load(DAILY)[True]
    assert "schedule" not in triggers, "the schedule must stay commented until activated"
    assert "workflow_dispatch" in triggers, "there must be a way to run it by hand"


def test_the_schedule_is_drafted_in_a_comment_ready_to_uncomment():
    text = DAILY.read_text(encoding="utf-8")
    assert "# schedule:" in text
    assert "# TO ACTIVATE" in text


def test_the_daily_workflow_calls_exactly_the_pipeline_entrypoint():
    """One command, not a pipeline spread across YAML steps."""
    commands = run_commands(load(DAILY), "pipeline")
    assert "python -m pipeline.daily" in commands

    for legacy in ("python -m models", "python -m drift.run", "python -m ingest"):
        assert legacy not in commands, (
            f"`{legacy}` is called directly from the workflow; the daily job must go "
            "through pipeline.daily so the whole chain stays testable locally"
        )


def test_the_daily_workflow_fails_fast_without_a_key():
    commands = run_commands(load(DAILY), "pipeline")
    assert "--require-eia-key" in commands, (
        "without this flag a cron would silently publish synthetic fixture numbers"
    )


def test_the_key_reaches_the_job_as_a_secret_and_is_never_echoed():
    daily = load(DAILY)
    text = DAILY.read_text(encoding="utf-8")

    env = [step.get("env", {}) for step in steps_of(daily, "pipeline")]
    assert any(e.get("EIA_API_KEY") == "${{ secrets.EIA_API_KEY }}" for e in env)

    lowered = text.lower()
    assert "echo $eia_api_key" not in lowered
    assert "echo ${{ secrets" not in lowered


def test_the_commit_step_stages_explicit_paths_only():
    """`git add metrics/` is one .gitignore mistake away from committing the lake."""
    commands = run_commands(load(DAILY), "pipeline", strip_comments=True)
    adds = [line.strip() for line in commands.splitlines() if line.strip().startswith("git add")]
    assert adds == ["git add metrics/forecast.json \\"], adds
    assert "git add ." not in commands
    assert "git add -A" not in commands
    assert "git add metrics/\n" not in commands


def test_the_committed_paths_are_exactly_what_the_pipeline_writes():
    from pipeline import daily as pipeline_daily

    commands = run_commands(load(DAILY), "pipeline")
    written = {
        pipeline_daily.FORECAST_JSON,
        pipeline_daily.MONITOR_JSON,
        pipeline_daily.DRIFT_JSON,
        pipeline_daily.DRIFT_SUMMARY,
        pipeline_daily.RUN_JSON,
        pipeline_daily.FORECAST_PNG,
        pipeline_daily.ROLLING_PNG,
    }
    for name in written:
        assert f"metrics/{name}" in commands, f"{name} is written but never committed"


def test_concurrency_stops_two_runs_writing_metrics_at_once():
    assert load(DAILY)["concurrency"]["group"]
    assert load(DAILY)["concurrency"]["cancel-in-progress"] is False


# ---------------------------------------------------------------------------
# ci.yml
# ---------------------------------------------------------------------------
def test_ci_lints_and_tests():
    commands = run_commands(load(CI), "test")
    assert "ruff check" in commands
    assert "pytest" in commands


def test_ci_smoke_tests_the_pipeline_and_the_drift_alarm():
    commands = run_commands(load(CI), "test")
    assert "python -m pipeline.daily" in commands
    assert "--simulate-shift" in commands, "CI must prove the drift alarm still fires"


def test_ci_guards_the_things_that_must_never_be_committed():
    commands = run_commands(load(CI), "test")
    assert "mlruns" in commands
    assert "5M" in commands, "the metrics/ size guard is what keeps the repo small"
