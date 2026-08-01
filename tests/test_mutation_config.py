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
RELEVANCE_SCRIPT = REPO / "scripts" / "mutation_relevance.py"
#: The canonical list of files that can move the score. It used to be the
#: `paths:` filter on mutation.yml's `pull_request` trigger; it moved here so
#: the `mutate` job could run — and therefore report — on every PR. See #19.
PATHS_FILE = REPO / ".github" / "mutation-paths.txt"


def _load(path: Path):
    """Import a committed script by path, without it being a package."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader, f"cannot import {path}"
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: modules here use `from __future__ import
    # annotations`, and dataclasses resolves those annotations via
    # sys.modules[cls.__module__]. Without this it raises AttributeError on None.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


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
    """The canonical path list and `[tool.mutmut].runner` must name the same tests.

    The PR trigger exists so the score is measured on the changes that can move
    it (ADR 0007, amended). That only holds while the list names every test file
    mutmut actually runs — add an eighth file to the runner, forget the list, and
    the job silently stops *doing* anything on the one change most likely to
    weaken the suite, while still reporting green. The failure mode is a workflow
    that looks configured and no longer covers what it claims to; since #19 it is
    strictly worse than it used to be, because the skip now reports success
    instead of not reporting at all.
    """
    triggers = workflow()[True]  # `on:` parses to the boolean True in YAML 1.1
    assert "pull_request" in triggers, (
        "mutation.yml no longer runs on pull requests, so a score regression "
        "would not be attributed to the change that caused it"
    )
    filtered = _canonical_patterns()

    runner = MUTMUT.get("runner", "")
    driving = set(re.findall(r"tests/\S+\.py", runner))
    assert driving, "[tool.mutmut].runner names no test files"

    missing = sorted(t for t in driving if not _matches_filter(t, filtered))
    assert not missing, (
        f"{missing} drive mutmut but are not matched by .github/mutation-paths.txt, "
        "so changing them would skip the mutation run and report green"
    )

    for target in targets():
        assert _matches_filter(target, filtered), (
            f"{target} is mutated but is not matched by .github/mutation-paths.txt, "
            "so changing it would skip the mutation run and report green"
        )


# ---------------------------------------------------------------------------
# What counts as a kill. This was inverted on both members at once, and no test
# could have caught it, because the two statuses it got wrong never appeared in
# any run on record -- `ok_suspicious` and `bad_timeout` are clock-dependent, so
# a fast runner never produces them and a slow one produces both.
# ---------------------------------------------------------------------------
def test_a_timeout_is_not_a_kill_and_a_slow_kill_is():
    """mutmut's own `ok_`/`bad_` prefix is the specification.

    From `mutmut/__init__.py::run_mutation`:

      * `BAD_TIMEOUT` is returned from `except TimeoutError` — the run was
        killed by the clock, and whether a test would have failed is unknown.
        Counting it as a kill credits the suite for a hang.
      * `OK_SUSPICIOUS` is returned when `not survived` — the tests *did* fail,
        so the mutant *is* dead — and it merely took longer than
        `test_time_base + baseline_time_elapsed * test_time_multiplier`.

    `scripts/mutation_score.py` had `{"ok_killed", "bad_timeout"}`: it credited
    the hang and discarded the genuine slow kill. On a shared runner that is
    worth several points of score against a floor with ~3 mutants of headroom.
    """
    module = _score_module()

    assert "ok_suspicious" in module.KILLED, (
        "`ok_suspicious` means the tests failed — the mutant was caught. Excluding "
        "it makes a slow runner look like a weakened suite."
    )
    assert "bad_timeout" not in module.KILLED, (
        "`bad_timeout` means the run hit the clock, not that a test failed. "
        "Counting it as a kill lets a hang inflate the score."
    )
    assert module.SURVIVED == "bad_survived"
    assert not (module.KILLED & module.UNRESOLVED), "a status cannot be both a kill and unresolved"
    assert module.SURVIVED not in module.KILLED


def test_a_timeout_lowers_the_score_and_is_named_in_the_report(tmp_path, monkeypatch, capsys):
    """The conservative direction, and visibly rather than silently."""
    cache = tmp_path / ".mutmut-cache"
    # 8 genuine kills, one of them slow; 1 survivor; 1 timeout.
    _fake_cache(cache, {"ok_killed": 7, "ok_suspicious": 1, "bad_survived": 1, "bad_timeout": 1})

    module = _score_module()
    monkeypatch.setattr(module, "CACHE", cache)
    monkeypatch.setattr("sys.argv", ["mutation_score.py", "--floor", "0", "--survivors", "0"])
    module.main()
    printed = capsys.readouterr().out

    # 8 killed of 10 -- the slow kill counts, the timeout does not.
    assert "**8** | **10** | **80.0%**" in printed, printed
    assert "neither killed nor survived" in printed, (
        "a timeout drags the score down; if the report does not say so, the drop "
        f"is indistinguishable from a real regression:\n{printed}"
    )


# ---------------------------------------------------------------------------
# The `paths:` filter must cover everything that can change the score, and
# "everything" is bigger than the files mutmut mutates. A mutant's fate depends
# on the whole import closure behind it: `drift/config.py` holds the
# DEFAULT_THRESHOLDS that tests/test_drift_boundaries.py pins, so editing a
# threshold there changes which mutants in drift/detectors.py die -- while
# touching no path the first version of this filter listed.
#
# Recomputed from the import graph rather than listed here, so the guard cannot
# be satisfied by editing the guard.
# ---------------------------------------------------------------------------
def _first_party_packages() -> set[str]:
    return {p.name for p in REPO.iterdir() if p.is_dir() and (p / "__init__.py").exists()}


def _resolve(dotted: str) -> str | None:
    path = REPO.joinpath(*dotted.split("."))
    if path.with_suffix(".py").exists():
        return f"{'/'.join(dotted.split('.'))}.py"
    if (path / "__init__.py").exists():
        return f"{'/'.join(dotted.split('.'))}/__init__.py"
    return None


def _import_closure(entrypoints: list[str]) -> set[str]:
    """Every first-party module reachable from `entrypoints` by import."""
    import ast

    packages = _first_party_packages()
    seen: set[str] = set()
    found: set[str] = set()

    def walk(rel: str) -> None:
        if rel in seen:
            return
        seen.add(rel)
        source = REPO / rel
        if not source.exists():
            return
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                # `from models import backtest` -- the submodule is in `names`,
                # not in `module`. Missing this hid five modules.
                candidates = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for dotted in candidates:
                if dotted.split(".")[0] not in packages:
                    continue
                resolved = _resolve(dotted)
                if resolved:
                    found.add(resolved)
                    walk(resolved)

    for entry in entrypoints:
        walk(entry)
    return found


def _canonical_patterns() -> list[str]:
    """The globs in `.github/mutation-paths.txt`, read the way the workflow reads them."""
    assert PATHS_FILE.exists(), (
        f"{PATHS_FILE.relative_to(REPO)} is missing. It is the single source of "
        "truth for which changes can move the mutation score — mutation.yml's "
        "relevance step and these tests both read it."
    )
    return _load(RELEVANCE_SCRIPT).load_patterns(PATHS_FILE)


def _matches_filter(path: str, patterns: list[str]) -> bool:
    """Delegated to the script the workflow actually runs.

    Not reimplemented here on purpose. A guard that matches paths its own way
    proves that *the test's* matcher covers the closure, which is not the claim
    being made — the claim is that the decision the workflow makes covers it.
    """
    return _load(RELEVANCE_SCRIPT).matches(path, list(patterns))


def test_the_paths_filter_covers_everything_the_mutation_run_reads():
    filtered = _canonical_patterns()
    runner_tests = sorted(re.findall(r"tests/\S+\.py", MUTMUT.get("runner", "")))

    closure = _import_closure([*targets(), *runner_tests])
    assert closure, "the import walk found nothing, so this guard is asserting nothing"

    missing = sorted(m for m in closure if not _matches_filter(m, filtered))
    assert not missing, (
        f"{missing} are imported by the mutated modules or by the tests that drive "
        "them, so changing one can change the score — but .github/mutation-paths.txt "
        "does not match them, so the mutation job would report green on that change "
        "without running."
    )


def test_the_paths_filter_covers_the_lockfile():
    """`uv sync --frozen` installs exactly `uv.lock`.

    A pandas/numpy/lightgbm bump changes behaviour under a suite nobody touched
    and matches no source path. It was originally argued that this is what the
    *cron* is for — "dependency change does not arrive in a commit" — but in
    this repository it usually does: Dependabot has opened four PRs here. A
    change that arrives in a commit should be caught by the trigger that can
    name the commit.
    """
    filtered = _canonical_patterns()
    assert (REPO / "uv.lock").exists()
    assert _matches_filter("uv.lock", filtered), (
        "uv.lock is not in .github/mutation-paths.txt, so a dependency bump "
        "would change what the tests do without re-measuring the score"
    )


# ---------------------------------------------------------------------------
# #19 — the `mutate` check must always report, so that `main` can require it.
#
# The old design narrowed the *trigger* with `paths:`. That is correct about
# which PRs deserve 36 minutes and fatal for a required check: a filtered-out PR
# produces no `mutate` check at all, and GitHub parks the PR at "Expected —
# Waiting for status to be reported" with no way through. Measured before branch
# protection went on, neither PR #16 nor PR #18 produced a `mutate` check.
#
# So the trigger is unconditional and the *work* is conditional. These guard the
# half of that which is easy to undo by accident.
# ---------------------------------------------------------------------------
def test_the_pull_request_trigger_has_no_paths_filter():
    """Re-adding `paths:` here would make `mutate` un-requireable again.

    This is the assertion that keeps #19 fixed. It looks like a tidy-up — the
    list is duplicated in `.github/mutation-paths.txt`, so why not filter with it
    too? — and it silently converts the check back into one that never reports on
    the PRs it skips.
    """
    trigger = workflow()[True]["pull_request"]
    assert not (trigger or {}).get("paths"), (
        "mutation.yml's pull_request trigger has a `paths:` filter again. A "
        "filtered-out PR produces no `mutate` check at all, which cannot be a "
        "required check: GitHub waits for a report that never comes. Narrow the "
        "work instead — .github/mutation-paths.txt and the `relevance` step."
    )
    assert not (trigger or {}).get("paths-ignore"), (
        "`paths-ignore` has the same effect on reporting as `paths`, and for a "
        "mixed PR the two are not even complementary."
    )


def test_the_job_itself_is_unconditional():
    """A job-level `if` is the other way to stop reporting."""
    job = workflow()["jobs"]["mutate"]
    assert "if" not in job, (
        f"the mutate job is gated by `if: {job.get('if')!r}`. The job must always "
        "run so the check always reports; gate the expensive steps instead."
    )


def _steps() -> list[dict]:
    return workflow()["jobs"]["mutate"]["steps"]


def test_the_relevance_step_decides_before_anything_expensive_happens():
    steps = _steps()
    relevance = [i for i, s in enumerate(steps) if s.get("id") == "relevance"]
    assert len(relevance) == 1, (
        "mutation.yml has no step with `id: relevance`, so nothing computes "
        "whether the 36-minute pass is needed"
    )
    index = relevance[0]

    assert "mutation_relevance.py" in str(steps[index].get("run", "")), (
        "the relevance step does not run scripts/mutation_relevance.py, so the "
        "decision is being made by something the tests do not read"
    )
    assert "python3" in str(steps[index].get("run", "")), (
        "the relevance step must use the system python3: it runs before "
        "`uv sync`, and installing a dependency tree to decide whether to do any "
        "work would spend the time this decision exists to save"
    )

    installs = [i for i, s in enumerate(steps) if "uv sync" in str(s.get("run", ""))]
    assert installs and min(installs) > index, (
        "dependencies are installed before relevance is decided, which pays part "
        "of the cost the skip exists to avoid"
    )

    checkout = [s for s in steps[:index] if str(s.get("uses", "")).startswith("actions/checkout")]
    assert checkout, "the relevance step diffs against the base but nothing checked the repo out"
    assert str(checkout[0].get("with", {}).get("fetch-depth")) == "0", (
        "checkout is shallow, so `git diff` against the base branch has no base "
        "to diff against. The step falls back to running the full pass, so this "
        "is a silent 36 minutes on every PR rather than a failure."
    )


def test_every_step_after_the_decision_is_gated_on_it():
    """Including the artifact upload, which fails a skipped run if it is not."""
    steps = _steps()
    index = next(i for i, s in enumerate(steps) if s.get("id") == "relevance")

    ungated = [
        s.get("name", s.get("uses"))
        for s in steps[index + 1 :]
        if "steps.relevance.outputs.relevant" not in str(s.get("if", ""))
    ]
    assert not ungated, (
        f"{ungated} run even when nothing relevant changed. Every step after the "
        "decision must be gated on `steps.relevance.outputs.relevant == 'true'` — "
        "the point of #19 is that the check reports in seconds on an irrelevant "
        "change, not that it reports after doing the work anyway."
    )

    uploads = [s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert uploads, "nothing is uploaded, so a failed run leaves nothing to diagnose it with"

    cache_upload = [u for u in uploads if ".mutmut-cache" in str(u.get("with", {}).get("path"))]
    assert len(cache_upload) == 1, "the mutmut cache is uploaded zero times or more than once"
    assert "always()" in str(cache_upload[0].get("if", "")), (
        "the cache upload no longer runs on failure, so a run that fails the "
        "floor leaves nothing to diagnose it with"
    )

    for upload in uploads:
        condition = str(upload.get("if", ""))
        if str(upload.get("with", {}).get("if-no-files-found")) == "error":
            assert "steps.relevance.outputs.relevant" in condition, (
                f"{upload.get('name')!r} is `if-no-files-found: error` under a bare "
                "`always()`. On a skipped run there is nothing to upload, so this "
                "would fail the very check #19 exists to make requireable."
            )


# ---------------------------------------------------------------------------
# The decision itself, exercised rather than described.
# ---------------------------------------------------------------------------
def _relevance():
    return _load(RELEVANCE_SCRIPT)


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        # The cases that must skip: this is the entire cost argument.
        (["README.md"], False),
        (["docs/MUTATION-TESTING.md", "CONTRIBUTING.md"], False),
        (["dashboard/src/App.tsx", "dashboard/package.json"], False),
        (["tests/test_doc_claims.py"], False),
        # The cases that must not. A mutated module, a driving test, a module in
        # the import closure, the lockfile, and the tooling that decides.
        (["drift/detectors.py"], True),
        (["models/backtest.py"], True),
        (["tests/test_backtest_accounting.py"], True),
        (["drift/config.py"], True),
        (["ingest/store.py"], True),
        (["uv.lock"], True),
        (["scripts/mutation_survivors.py"], True),
        (["pyproject.toml"], True),
        # The dotfile paths, and every one of them a live hole while `matches()`
        # used `lstrip("./")` — which strips *characters*, so `.github/...`
        # arrived as `github/...` and matched nothing. A PR could lower the
        # floor, delete a gate, or edit the killed-set baseline and be judged
        # irrelevant, reporting `mutate` green without running it. This table had
        # no dotfile row, which is how 316 tests passed over a dead matcher.
        ([".github/workflows/mutation.yml"], True),
        ([".github/mutation-paths.txt"], True),
        ([".github/mutation-baseline.json"], True),
        (["scripts/mutation_ratchet.py"], True),
        (["scripts/mutation_relevance.py"], True),
        # A leading `./` is the one prefix that must be stripped, and stripping
        # it must not eat the dot of a dotfile behind it.
        (["./drift/detectors.py"], True),
        # Mixed: one relevant path in a hundred is still relevant. This is the
        # case `paths` + `paths-ignore` gets wrong, per #19's rejected design.
        (["README.md", "docs/adr/0007.md", "drift/detectors.py"], True),
        # An empty diff is not relevant — and must not be confused with a diff
        # that could not be computed, which the workflow handles separately.
        ([], False),
    ],
)
def test_the_relevance_decision_matches_what_can_move_the_score(changed, expected):
    module = _relevance()
    patterns = module.load_patterns(PATHS_FILE)
    assert bool(module.select(changed, patterns)) is expected, (
        f"{changed} was judged {'relevant' if not expected else 'irrelevant'}. "
        f"A false negative reports green without measuring anything; a false "
        f"positive costs 36 minutes."
    )


def test_every_literal_entry_in_the_canonical_list_matches_itself():
    """The generic form of the `lstrip("./")` bug, rather than a row per path.

    Enumerating cases in the table above only ever catches the paths someone
    thought to enumerate; this catches any future normalisation that mangles a
    path on its way into the matcher. A pattern that does not match its own text
    is a pattern that can never fire, and a pattern that can never fire is a hole
    that reports the `mutate` check green without running it.
    """
    module = _relevance()
    patterns = module.load_patterns(PATHS_FILE)
    literals = [p for p in patterns if not any(ch in p for ch in "*?[")]
    assert literals, "the canonical list is all globs — this guard asserts nothing"
    dead = [p for p in literals if not module.matches(p, patterns)]
    assert not dead, (
        f"{dead} appear in .github/mutation-paths.txt but do not match themselves, "
        "so changing those files would skip the mutation run and report green"
    )


def test_the_diff_the_workflow_takes_cannot_mangle_a_path():
    """Both flags fix a silent skip, and a silent skip here reports success.

    `core.quotepath` renders a non-ASCII path as `"drift/caf\\303\\251.py"` —
    quotes and octal escapes included — which matches no pattern. Rename
    detection reports only the *new* name, so renaming a mutated module to an
    unlisted path would look irrelevant.
    """
    steps = workflow()["jobs"]["mutate"]["steps"]
    relevance = next(s for s in steps if s.get("id") == "relevance")
    # Comments stripped first, and the whole invocation asserted rather than the
    # flag names. The first version of this guard could not fail: the step's own
    # comment explains both flags by name, so deleting them from the command
    # while leaving the prose that praises them kept every assertion true. A
    # guard satisfiable by its own documentation is the same defect as
    # `assert ... or True`, wearing a better disguise.
    command = "\n".join(
        line
        for line in str(relevance.get("run", "")).splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "git -c core.quotepath=off diff --name-only --no-renames" in command, (
        "the relevance step's actual diff command lost `core.quotepath=off` or "
        "`--no-renames`. Without the first, a non-ASCII path arrives quoted and "
        "octal-escaped and matches nothing; without the second, a rename reports "
        "only the new name. Both skip the run silently, and a skip reports green."
    )


def test_the_canonical_list_ignores_comments_and_blank_lines():
    """Otherwise the prose in that file becomes patterns matching nothing, or worse."""
    module = _relevance()
    patterns = module.load_patterns(PATHS_FILE)
    assert patterns, "the canonical list parsed to nothing"
    assert not [p for p in patterns if p.startswith("#") or not p.strip()], (
        f"comments or blank lines survived parsing: {patterns}"
    )
    # The file is heavily commented on purpose; if that stopped being true the
    # reasoning moved somewhere this test cannot see.
    raw = PATHS_FILE.read_text(encoding="utf-8").splitlines()
    assert len([ln for ln in raw if ln.strip().startswith("#")]) > len(patterns) / 2, (
        "the canonical path list has lost the reasoning that says why each entry "
        "is in it — which is the part that stops it rotting"
    )
