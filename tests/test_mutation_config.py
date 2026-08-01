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


# ---------------------------------------------------------------------------
# The document that publishes the score. It drifted once: after the run that
# took 52.3% to 61.2%, the header and the gap section were updated while the
# accepted-survivors table kept the previous run's counts (summing to 188
# against a stated 163) and the closing bullets still said 52.3%, 226
# survivors and 38 gaps. Nothing read the document as a whole, so it disagreed
# with itself for a day. These assertions are pure arithmetic over the doc's
# own tables — no mutmut cache needed — so they run everywhere pytest does,
# including the pre-flight step of the mutation workflow.
# ---------------------------------------------------------------------------

DOC = REPO / "docs" / "MUTATION-TESTING.md"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _stated_totals(doc: str) -> tuple[int, int, float, int]:
    stated = re.search(
        r"\*\*(\d+) mutants across (\d+) source lines\.\s+(\d+) are real gaps "
        r"\((\d+\.\d)%\);\s+(\d+) are\s+accepted\.\*\*",
        doc,
    )
    assert stated, "MUTATION-TESTING.md no longer states its survivor totals"
    n_mutants, _n_lines, n_gaps, gap_pct, n_accepted = (
        int(stated.group(1)),
        int(stated.group(2)),
        int(stated.group(3)),
        float(stated.group(4)),
        int(stated.group(5)),
    )
    return n_mutants, n_gaps, gap_pct, n_accepted


def test_the_mutation_doc_agrees_with_itself():
    doc = _doc()

    total_row = re.search(
        r"\| \*\*Total\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \| \*\*(\d+\.\d)%\*\* \|", doc
    )
    assert total_row, "the score table no longer has a Total row"
    killed, total, score = (
        int(total_row.group(1)),
        int(total_row.group(2)),
        float(total_row.group(3)),
    )
    assert round(100 * killed / total, 1) == score, "the Total row's score is not killed/total"

    # `killed + survived == total` is NOT an identity: mutmut also reports
    # `untested` mutants, which the score counts as not-killed. This assumed
    # otherwise and was off by exactly that count, so the doc has to state the
    # number and the arithmetic has to use it. That makes the disclosure
    # load-bearing rather than decorative -- delete the sentence and this fails.
    untested = re.search(r"\*\*(\d+) mutants mutmut never tested\*\*", doc)
    assert untested, (
        "the doc no longer discloses how many mutants went untested. The score "
        "counts them as not-killed, so an undisclosed count is a silent hole in "
        "the denominator."
    )
    survivors = total - killed - int(untested.group(1))

    headline = re.search(r"The headline number is (\d+\.\d)%", doc)
    assert headline, "the doc no longer opens with the headline score"
    assert float(headline.group(1)) == score

    adjudicated = re.search(r"Every one of the (\d+) survivors is adjudicated", doc)
    assert adjudicated, "the adjudication heading no longer states the survivor count"
    assert int(adjudicated.group(1)) == survivors

    n_mutants, n_gaps, gap_pct, n_accepted = _stated_totals(doc)
    assert n_mutants == survivors, (
        f"the doc adjudicates {n_mutants} survivors but its score table implies {survivors}"
    )
    assert n_gaps + n_accepted == n_mutants
    assert round(100 * n_gaps / n_mutants, 1) == gap_pct

    gaps_heading = re.search(r"### The gaps — (\d+) mutants", doc)
    assert gaps_heading and int(gaps_heading.group(1)) == n_gaps
    accepted_heading = re.search(r"### The accepted survivors — (\d+) mutants", doc)
    assert accepted_heading, "the accepted-survivors heading no longer states a count"
    assert int(accepted_heading.group(1)) == n_accepted, (
        f"the accepted-survivors heading says {accepted_heading.group(1)} "
        f"but the stated totals say {n_accepted}"
    )


def test_the_survivor_tables_sum_to_their_stated_totals():
    """The drift that actually happened: a regenerated header over a stale table."""
    doc = _doc()
    rows = re.findall(r"^\| `((?:gap|accepted):[a-z-]+)` \| (\d+) \| (\d+) \|", doc, flags=re.M)
    assert rows, "the doc no longer carries per-rule survivor tables"
    gap_sum = sum(int(m) for rule, _lines, m in rows if rule.startswith("gap:"))
    accepted_sum = sum(int(m) for rule, _lines, m in rows if rule.startswith("accepted:"))
    _n_mutants, n_gaps, _gap_pct, n_accepted = _stated_totals(doc)
    assert gap_sum == n_gaps, f"the gap table sums to {gap_sum}, the doc claims {n_gaps}"
    assert accepted_sum == n_accepted, (
        f"the accepted table sums to {accepted_sum}, the doc claims {n_accepted}"
    )


def test_every_rule_the_doc_tabulates_exists_in_the_adjudication_script():
    """A table row naming a rule the script deleted describes a codebase that is gone."""
    doc = _doc()
    script = SURVIVOR_SCRIPT.read_text(encoding="utf-8")
    rules = {
        rule
        for rule, _lines, _m in re.findall(
            r"^\| `((?:gap|accepted):[a-z-]+)` \| (\d+) \| (\d+) \|", doc, flags=re.M
        )
    }
    assert rules
    for rule in sorted(rules):
        assert f'"{rule}"' in script, (
            f"MUTATION-TESTING.md tabulates {rule!r} but scripts/mutation_survivors.py "
            "no longer declares it"
        )


# ---------------------------------------------------------------------------
# The floor must be enforced against the number the report prints.
#
# The bug this pins shipped and was never observed, because the workflow had
# run exactly once in its history and that run used a different floor: the
# published score is 308/474 = 64.9789%, which `scripts/mutation_score.py`
# prints as "65.0%", and the floor read straight off that published figure was
# 65. So the gate failed on the very measurement that produced it, and the job
# summary would have shown "**65.0%**" in the table and "65.0% is below the
# floor of 65.0%" underneath. Comparing the rounded value makes the two agree.
# ---------------------------------------------------------------------------
def _fake_cache(path: Path, statuses: dict[str, int]) -> None:
    """Write the three tables `scripts/mutation_score.py` reads."""
    import sqlite3

    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table SourceFile (id integer primary key, filename text);
        create table Line (id integer primary key, line_number int, line text, sourcefile int);
        create table Mutant (id integer primary key, line int, status text);
        insert into SourceFile values (1, 'drift/detectors.py');
        """
    )
    mutant_id = 0
    for status, count in statuses.items():
        for _ in range(count):
            mutant_id += 1
            conn.execute("insert into Line values (?, ?, ?, 1)", (mutant_id, mutant_id, "x = 1"))
            conn.execute("insert into Mutant values (?, ?, ?)", (mutant_id, mutant_id, status))
    conn.commit()
    conn.close()


def _score_module():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("mutation_score", SCORE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


# The exact published measurement: 308 killed of 474, with the 9 mutmut never
# tested counted as not-killed, as the score does.
PUBLISHED = {"ok_killed": 308, "bad_survived": 157, "untested": 9}


@pytest.mark.parametrize(
    ("floor", "expected_exit"),
    [
        (65.0, 0),  # the score prints as 65.0%; 65.0 is not below 65.0
        (64.0, 0),
        (65.1, 1),  # genuinely below — the gate must still bite
        (70.0, 1),
    ],
)
def test_the_floor_is_enforced_against_the_reported_score(
    tmp_path, monkeypatch, capsys, floor: float, expected_exit: int
):
    cache = tmp_path / ".mutmut-cache"
    _fake_cache(cache, PUBLISHED)

    module = _score_module()
    monkeypatch.setattr(module, "CACHE", cache)
    monkeypatch.setattr(
        "sys.argv", ["mutation_score.py", "--floor", str(floor), "--survivors", "0"]
    )

    exit_code = module.main()
    printed = capsys.readouterr().out

    assert "**65.0%**" in printed, f"the report no longer prints 65.0% for 308/474:\n{printed}"
    assert exit_code == expected_exit, (
        f"floor {floor} gave exit {exit_code}, expected {expected_exit}. Report was:\n{printed}"
    )
    # Whatever the verdict, it must quote the same number the table shows.
    verdict = [ln for ln in printed.splitlines() if "floor of" in ln]
    assert verdict, f"no verdict line in:\n{printed}"
    assert "65.0%" in verdict[0], (
        f"the verdict quotes a different number than the table: {verdict[0]!r}"
    )


def test_the_pull_request_paths_filter_covers_every_test_that_drives_mutmut():
    """The `paths:` filter and `[tool.mutmut].runner` must name the same tests.

    The PR trigger exists so the score is measured on the changes that can move
    it (ADR 0007, amended). That only holds while the filter lists every test
    file mutmut actually runs — add an eighth file to the runner, forget the
    filter, and the job silently stops firing on the one change most likely to
    weaken the suite. The failure mode is a workflow that looks configured and
    no longer covers what it claims to.
    """
    triggers = workflow()[True]  # `on:` parses to the boolean True in YAML 1.1
    assert "pull_request" in triggers, (
        "mutation.yml no longer runs on pull requests, so a score regression "
        "would not be attributed to the change that caused it"
    )
    filtered = set(triggers["pull_request"].get("paths", []))
    assert filtered, "the pull_request trigger has no paths filter"

    runner = MUTMUT.get("runner", "")
    driving = set(re.findall(r"tests/\S+\.py", runner))
    assert driving, "[tool.mutmut].runner names no test files"

    missing = driving - filtered
    assert not missing, (
        f"{sorted(missing)} drive mutmut but are not in mutation.yml's paths "
        "filter, so changing them would not trigger the job"
    )

    for target in targets():
        assert target in filtered, (
            f"{target} is mutated but is not in mutation.yml's paths filter, so "
            "changing it would not trigger the job"
        )
