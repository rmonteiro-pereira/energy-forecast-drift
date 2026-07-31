"""The mutation setup must actually be capable of running.

A mutation config aimed at a path that does not exist reports a perfect score
over zero mutants, and a workflow with `if: false` reports nothing at all while
looking present in the repository. Both produce a green tick and a number nobody
earned, which is worse than having no mutation testing: it converts an absence
into a false claim of rigour.

So the config is asserted rather than assumed. These tests are also the first
step of the mutation workflow itself, so a broken config fails in seconds
instead of after a 25-minute run over nothing.

The score these guard is reported in `docs/MUTATION-TESTING.md`.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
MUTMUT = PYPROJECT.get("tool", {}).get("mutmut", {})
WORKFLOW = REPO / ".github" / "workflows" / "mutation.yml"
SCORE_SCRIPT = REPO / "scripts" / "mutation_score.py"
SURVIVOR_SCRIPT = REPO / "scripts" / "mutation_survivors.py"


def targets() -> list[str]:
    paths = MUTMUT.get("paths_to_mutate", "")
    return [p.strip() for p in paths.split(",") if p.strip()]


def test_a_mutation_config_exists_at_all():
    assert MUTMUT, "[tool.mutmut] is missing from pyproject.toml"
    assert targets(), "paths_to_mutate is empty — mutmut would mutate nothing"


@pytest.mark.parametrize("target", targets())
def test_every_mutation_target_exists_and_has_code(target: str):
    """The Mall-lane failure mode: a config aimed at directories that do not exist."""
    path = REPO / target
    assert path.exists(), (
        f"paths_to_mutate names {target!r}, which does not exist. mutmut would "
        "generate zero mutants and report a perfect score over nothing."
    )
    body = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(body) > 50, f"{target} has only {len(body)} code lines — is this the right target?"


def test_the_targets_are_the_two_documented_ones():
    """Scope is a decision (ADR 0007), so widening it silently should be visible."""
    assert set(targets()) == {"drift/detectors.py", "models/backtest.py"}, (
        f"mutation scope changed to {targets()}. That is allowed, but update "
        "docs/adr/0007 and docs/MUTATION-TESTING.md so the reported score still "
        "describes what was actually measured."
    )


@pytest.mark.parametrize("test_file", re.findall(r"tests/\S+\.py", MUTMUT.get("runner", "")))
def test_every_test_file_in_the_runner_exists(test_file: str):
    """A runner naming a missing test file kills nothing and survives everything."""
    assert (REPO / test_file).exists(), (
        f"the mutmut runner names {test_file!r}, which does not exist. pytest "
        "would error, every mutant would look 'killed', and the score would be a lie."
    )


def test_the_runner_actually_invokes_pytest():
    runner = MUTMUT.get("runner", "")
    assert "pytest" in runner, f"the mutmut runner does not run pytest: {runner!r}"
    assert re.search(r"tests/\S+\.py", runner), (
        "the runner names no test files, so mutmut would run the whole suite per "
        "mutant — correct but far too slow to ever finish"
    )


def test_the_score_script_is_committed():
    """The reported number has to be regenerable by someone who is not me."""
    assert SCORE_SCRIPT.exists(), "scripts/mutation_score.py is missing"
    assert "floor" in SCORE_SCRIPT.read_text(encoding="utf-8")


def test_every_adjudication_rule_carries_a_written_reason():
    """A rule with an empty reason is an undecided survivor wearing a label.

    The failure this guards against: a mutation report that lists hundreds of
    survivors and decides nothing about any of them. Each rule in
    `scripts/mutation_survivors.py` must state a verdict *and* say why, in
    enough words to be an argument rather than a shrug.
    """
    assert SURVIVOR_SCRIPT.exists(), "scripts/mutation_survivors.py is missing"

    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("mutation_survivors", SURVIVOR_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: the module defines a dataclass under
    # `from __future__ import annotations`, and dataclasses resolves those
    # annotations via sys.modules[cls.__module__]. Without this it raises
    # AttributeError on None.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    assert module.RULES, "no adjudication rules are defined"
    for rule in module.RULES:
        assert rule.verdict in {module.ACCEPTED, module.GAP}, (
            f"rule {rule.name!r} has verdict {rule.verdict!r}, which is neither "
            f"{module.ACCEPTED} nor {module.GAP}"
        )
        assert len(rule.reason.split()) >= 12, (
            f"rule {rule.name!r} has a {len(rule.reason.split())}-word reason. "
            "State the argument, not a label — this is the field that stops the "
            "report being decoration."
        )
        assert rule.pattern is not None or rule.locations, (
            f"rule {rule.name!r} matches nothing, so it adjudicates nothing"
        )

    gaps = [r for r in module.RULES if r.verdict == module.GAP]
    assert gaps, (
        "every rule is ACCEPTED. A survivor set with no acknowledged gaps in it "
        "is a sign the adjudication is rationalising rather than judging."
    )


def test_the_workflow_gates_on_adjudication_not_just_on_the_score():
    steps = workflow()["jobs"]["mutate"]["steps"]
    adjudication = [s for s in steps if "mutation_survivors.py" in str(s.get("run", ""))]
    assert len(adjudication) == 1, (
        "mutation.yml never runs scripts/mutation_survivors.py, so an "
        "unadjudicated survivor would pass unnoticed"
    )
    assert "--check" in str(adjudication[0]["run"]), (
        "the adjudication step runs without --check, so it reports but never fails"
    )


# ---------------------------------------------------------------------------
# the workflow
# ---------------------------------------------------------------------------
def workflow() -> dict:
    yaml = pytest.importorskip("yaml")
    assert WORKFLOW.exists(), ".github/workflows/mutation.yml is missing"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_mutation_workflow_is_not_disabled():
    """`if: false` is how a workflow looks present while doing nothing.

    Checked against the parsed YAML and against non-comment lines only. An
    earlier version scanned the raw text and flagged this file's own header
    comment explaining that it contains no `if: false` — a guard that fires on
    the sentence describing it is not a guard.
    """
    parsed = workflow()

    job_level = str(parsed["jobs"]["mutate"].get("if", "")).strip().lower()
    assert job_level not in {"false", "${{ false }}"}, "the mutate job is disabled at job level"

    steps = parsed["jobs"]["mutate"]["steps"]
    for step in steps:
        condition = str(step.get("if", "")).strip().lower()
        assert condition not in {"false", "${{ false }}"}, (
            f"step {step.get('name', step.get('uses'))!r} is disabled with `if: false`. "
            "If it should not run, delete it rather than leaving it looking present."
        )

    code_lines = [
        line
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    offenders = [line for line in code_lines if re.search(r"\bif:\s*false\b", line, re.IGNORECASE)]
    assert not offenders, f"`if: false` in mutation.yml: {offenders}"

    run_step = [s for s in steps if "mutmut run" in str(s.get("run", ""))]
    assert len(run_step) == 1, "mutation.yml does not run `mutmut run` exactly once"


def test_the_mutation_workflow_can_actually_be_triggered():
    triggers = workflow()[True]  # `on:` parses to the boolean True in YAML 1.1
    assert "schedule" in triggers or "workflow_dispatch" in triggers, (
        "mutation.yml has no schedule and no manual trigger, so it can never run"
    )


def test_the_workflow_enforces_a_floor_rather_than_trusting_the_exit_code():
    """`mutmut run` always exits non-zero here; the verdict must come from the score."""
    steps = workflow()["jobs"]["mutate"]["steps"]
    scoring = [s for s in steps if "mutation_score.py" in str(s.get("run", ""))]
    assert len(scoring) == 1, "mutation.yml never invokes scripts/mutation_score.py"
    assert "--floor" in str(scoring[0]["run"]), (
        "the scoring step sets no floor, so a regression in test strength would still report green"
    )


def test_the_workflow_pins_the_same_interpreter_as_ci():
    """Same trap as ci.yml — see tests/test_toolchain.py."""
    pinned = (REPO / ".python-version").read_text(encoding="utf-8").strip()
    setup = [
        s
        for s in workflow()["jobs"]["mutate"]["steps"]
        if str(s.get("uses", "")).startswith("astral-sh/setup-uv")
    ]
    assert len(setup) == 1
    assert str(setup[0].get("with", {}).get("python-version", "")).strip() == pinned
