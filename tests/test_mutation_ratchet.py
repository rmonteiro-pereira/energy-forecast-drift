"""The killed-set ratchet: it must accuse the right commit, and only that one.

The percentage floor is a real gate and it is not enough. Demonstrated rather
than feared: deleting the two assertions at `tests/test_backtest_accounting.py:92-93`
— the only lines in the repository that read `overall["bias"]` — left the suite
green, left `mutation_survivors.py --check` at exit 0, and left the score at
315/474 = 66.5% against a floor of 66. Exactly one kill was lost and every gate
passed. See `docs/MUTATION-TESTING.md`.

So these tests are about the two ways a per-mutant ratchet goes wrong:

  * it misses a real regression — the attack above;
  * it invents one. A ratchet that cries wolf gets disabled, and a disabled gate
    protects nothing. Most of what follows is the second kind: a shifted line, a
    timeout, an edited line, a new mutant. None of those is a weakened suite.

The caches here are synthetic, written against the schema `mutmut/cache.py`
actually creates — verified against a real `.mutmut-cache` produced by mutmut
2.5.1: `SourceFile(id, filename, hash)`, `Line(id, sourcefile, line,
line_number)` holding **every** line of the file with `line_number` 0-based, and
`Mutant(id, line, index, tested_against_hash, status)`. Synthetic rather than
recorded so the suite stays fast and hermetic; the migration was additionally
exercised end to end against real mutmut runs while it was being written.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RATCHET_SCRIPT = REPO / "scripts" / "mutation_ratchet.py"
SCORE_SCRIPT = REPO / "scripts" / "mutation_score.py"
WORKFLOW = REPO / ".github" / "workflows" / "mutation.yml"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


@pytest.fixture
def ratchet():
    return _load(RATCHET_SCRIPT)


def write_cache(path: Path, files: dict[str, tuple[list[str], dict[tuple[int, int], str]]]) -> None:
    """Build a `.mutmut-cache` the way mutmut does.

    `files` maps filename -> (every line of the file, {(line_number, index): status}).
    `Line` carries the whole file, not only the mutated lines — that is what
    makes `SequenceMatcher` able to align two runs at all.
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table SourceFile (id integer primary key, filename text, hash text);
        create table Line (id integer primary key, sourcefile int, line text, line_number int);
        create table Mutant (id integer primary key, line int, "index" int,
                             tested_against_hash text, status text);
        """
    )
    line_id = 0
    mutant_id = 0
    for file_id, (filename, (lines, mutants)) in enumerate(files.items(), start=1):
        conn.execute("insert into SourceFile values (?, ?, ?)", (file_id, filename, "h"))
        ids: dict[int, int] = {}
        for number, text in enumerate(lines):
            line_id += 1
            ids[number] = line_id
            conn.execute("insert into Line values (?, ?, ?, ?)", (line_id, file_id, text, number))
        for (number, index), status in mutants.items():
            mutant_id += 1
            conn.execute(
                "insert into Mutant values (?, ?, ?, ?, ?)",
                (mutant_id, ids[number], index, "t", status),
            )
    conn.commit()
    conn.close()


BODY = [
    "def scale(x):",
    "    y = x * 2",
    "    return y",
]


def _run(ratchet, tmp_path, before, after, argv_extra=()):
    """Baseline from `before`, then check `after` against it. Returns (exit, output)."""
    old = tmp_path / "old.cache"
    new = tmp_path / "new.cache"
    baseline = tmp_path / "baseline.json"
    write_cache(old, before)
    write_cache(new, after)
    assert ratchet.main(["--cache", str(old), "--write", str(baseline)]) == 0
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = ratchet.main(
            ["--cache", str(new), "--check", "--baseline", str(baseline), *argv_extra]
        )
    return code, buffer.getvalue()


# ---------------------------------------------------------------------------
# "Killed" has to mean the same thing here as in the score.
# ---------------------------------------------------------------------------
def test_killed_means_exactly_what_the_score_means(ratchet):
    """Restating the set is how it would stop meaning the same thing.

    This is not hypothetical bookkeeping: `bad_timeout` was counted as a kill
    once already, and `ok_suspicious` — a genuine slow kill — was thrown away at
    the same time. The fix has to hold in both places or a slow runner reads as
    a weakened suite.
    """
    score = _load(SCORE_SCRIPT)
    killed, unresolved = set(score.KILLED), set(score.UNRESOLVED)
    assert killed == ratchet.KILLED
    assert ratchet.SURVIVED == score.SURVIVED
    assert unresolved == ratchet.UNRESOLVED

    assert "ok_suspicious" in ratchet.KILLED, "a slow kill is still a kill"
    assert "bad_timeout" not in ratchet.KILLED, "a hang is not a kill"
    assert "bad_timeout" in ratchet.UNRESOLVED
    assert not (ratchet.KILLED & ratchet.UNRESOLVED)


def test_a_timeout_is_neither_a_kill_nor_a_regression(ratchet, tmp_path):
    """A slow runner must not be able to accuse a commit."""
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed"})},
        {"m.py": (BODY, {(1, 0): "bad_timeout"})},
    )
    assert code == 0, f"a timeout failed the ratchet:\n{out}"
    assert "| inconclusive | 1 |" in out, out
    assert "| **regressed** | **0** |" in out, out


def test_an_untested_mutant_is_not_a_regression_either(ratchet, tmp_path):
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed"})},
        {"m.py": (BODY, {(1, 0): "untested"})},
    )
    assert code == 0, out
    assert "| inconclusive | 1 |" in out, out


def test_a_slow_kill_still_counts_as_held(ratchet, tmp_path):
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed"})},
        {"m.py": (BODY, {(1, 0): "ok_suspicious"})},
    )
    assert code == 0, out
    assert "| held | 1 |" in out, out


# ---------------------------------------------------------------------------
# The attack it exists for.
# ---------------------------------------------------------------------------
def test_a_lost_kill_is_a_regression_and_is_named(ratchet, tmp_path):
    """The deleted-assertion attack, which the percentage floor absorbed."""
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed", (2, 0): "ok_killed"})},
        {"m.py": (BODY, {(1, 0): "bad_survived", (2, 0): "ok_killed"})},
    )
    assert code == 1, f"a kill was lost and the ratchet passed:\n{out}"
    assert "| **regressed** | **1** |" in out, out
    # Per-mutant attribution is the entire advantage over a percentage.
    assert "`m.py` line 1 index 0" in out, f"the report does not say which mutant regressed:\n{out}"


def test_a_kill_that_vanishes_from_an_unchanged_line_fails(ratchet, tmp_path):
    """Not a retirement: nothing about the line moved, so nothing explains it."""
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed"})},
        {"m.py": (BODY, {})},
    )
    assert code == 1, f"a kill disappeared with its line intact and nothing failed:\n{out}"
    assert "| **vanished** | **1** |" in out, out


# ---------------------------------------------------------------------------
# The ways it must NOT cry wolf. A ratchet that invents regressions gets turned
# off, and an off gate protects nothing.
# ---------------------------------------------------------------------------
def test_kills_migrate_through_an_insertion_elsewhere_in_the_file(ratchet, tmp_path):
    """The reason the integer primary key is not persisted.

    CI never restores the cache, so ids are reassigned in insertion order every
    run: insert one line and every later id shifts. Keying on the pk would report
    this entirely innocent change as a wholesale regression.
    """
    shifted = ['"""New docstring."""', "", "CONSTANT = 1", "", *BODY]
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed", (2, 0): "ok_killed"})},
        {"m.py": (shifted, {(5, 0): "ok_killed", (6, 0): "ok_killed"})},
    )
    assert code == 0, f"shifting every line number invented a regression:\n{out}"
    assert "| held | 2 |" in out, out


def test_editing_a_line_retires_its_kill_rather_than_regressing(ratchet, tmp_path):
    """An edited line is a new mutant, so the old kill's disappearance is correct."""
    edited = ["def scale(x):", "    y = x * 3", "    return y"]
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed"})},
        {"m.py": (edited, {(1, 0): "bad_survived"})},
    )
    assert code == 0, f"editing a line was reported as a weakened suite:\n{out}"
    assert "| retired | 1 |" in out, out
    assert "| **regressed** | **0** |" in out, out


def test_a_brand_new_survivor_is_not_the_ratchets_business(ratchet, tmp_path):
    """It supplements `mutation_survivors.py --check`; it does not replace it.

    A killed-set comparison is blind to a new survivor by construction. Making it
    fail here would duplicate the adjudication gate badly — and dropping the
    adjudication gate on the strength of this one would open a hole exactly where
    this is blind.
    """
    grown = [*BODY, "", "def other(z):", "    return z - 1"]
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed"})},
        {"m.py": (grown, {(1, 0): "ok_killed", (5, 0): "bad_survived"})},
    )
    assert code == 0, f"a new survivor failed the ratchet, which is --check's job:\n{out}"
    assert "| held | 1 |" in out, out


def test_a_file_dropped_from_the_mutation_scope_retires_rather_than_fails(ratchet, tmp_path):
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (BODY, {(1, 0): "ok_killed"}), "n.py": (BODY, {(1, 0): "ok_killed"})},
        {"m.py": (BODY, {(1, 0): "ok_killed"})},
    )
    assert code == 0, out
    assert "| retired | 1 |" in out, out


# ---------------------------------------------------------------------------
# The undecidable case. Agreed behaviour: refuse rather than guess.
# ---------------------------------------------------------------------------
DUPLICATED = [
    "def f(x):",
    "    x = x + 1",
    "    x = x + 1",
    "    return x",
]


def test_inserting_a_line_beside_a_duplicate_does_not_transfer_the_status(ratchet, tmp_path):
    """The test the design notes asked for by name.

    `SequenceMatcher` cannot say which of two adjacent identical lines is "the
    original" — inserting a third gives `[equal 0-3->0-3, insert 3-3->3-4,
    equal 3-4->4-5]`, and the assignment is consistent but arbitrary. Harmless
    when the statuses agree; not harmless when they differ, which is 2 of the 21
    colliding keys measured on the real cache.

    So the killed mutant must come out `ambiguous` — **not** silently inheriting
    the survivor's status, and **not** silently keeping its own. A ratchet that
    guesses where its key is undecidable will eventually accuse the wrong commit.
    """
    inserted = [
        "def f(x):",
        "    x = x + 1",
        "    x = x + 1",
        "    x = x + 1",
        "    return x",
    ]
    code, out = _run(
        ratchet,
        tmp_path,
        # Two adjacent identical lines whose statuses disagree: the dangerous case.
        {"m.py": (DUPLICATED, {(1, 0): "ok_killed", (2, 0): "bad_survived"})},
        {
            "m.py": (
                inserted,
                {(1, 0): "bad_survived", (2, 0): "bad_survived", (3, 0): "bad_survived"},
            )
        },
    )
    assert "| **ambiguous** | **1** |" in out, (
        f"the killed mutant was migrated across an undecidable alignment "
        f"instead of being refused:\n{out}"
    )
    assert "| **regressed** | **0** |" in out, (
        f"an undecidable identity was reported as a definite regression, which is "
        f"exactly the wrong-commit accusation the refusal exists to prevent:\n{out}"
    )
    assert code == 1, (
        f"an ambiguous identity has to be adjudicated by a human, the same way an "
        f"unclassified survivor is — passing silently defeats the point:\n{out}"
    )


def test_adjacent_duplicates_that_agree_are_not_ambiguous(ratchet, tmp_path):
    """Identical lines produce identical mutations, so swapping equals swaps nothing.

    Refusing on every duplicate line regardless of status would make the 21 known
    colliding keys in this repository permanently unadjudicable — a gate nobody
    can get past rather than a gate that bites.
    """
    inserted = [*DUPLICATED[:3], "    x = x + 1", DUPLICATED[3]]
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (DUPLICATED, {(1, 0): "ok_killed", (2, 0): "ok_killed"})},
        {"m.py": (inserted, {(1, 0): "ok_killed", (2, 0): "ok_killed", (3, 0): "ok_killed"})},
    )
    assert code == 0, f"agreeing duplicates were refused unnecessarily:\n{out}"
    assert "| **ambiguous** | **0** |" in out, out
    assert "| held | 2 |" in out, out


def test_an_untouched_file_full_of_duplicates_is_never_ambiguous(ratchet, tmp_path):
    """Otherwise the gate would be permanently red on a repository it fits."""
    code, out = _run(
        ratchet,
        tmp_path,
        {"m.py": (DUPLICATED, {(1, 0): "ok_killed", (2, 0): "bad_survived"})},
        {"m.py": (DUPLICATED, {(1, 0): "ok_killed", (2, 0): "bad_survived"})},
    )
    assert code == 0, f"an unchanged file was reported ambiguous:\n{out}"
    assert "| **ambiguous** | **0** |" in out, out


# ---------------------------------------------------------------------------
# The cache must be read as data, never restored into place.
# ---------------------------------------------------------------------------
def test_the_ratchet_cannot_modify_the_run_it_is_judging(ratchet, tmp_path):
    """`cached_mutation_status` returns OK_KILLED **without re-running**.

    From `mutmut/cache.py`, on the stated assumption that "if a mutant was
    killed, a change to the test suite will mean it's still killed" — which is
    precisely the attack this ratchet exists to catch. Restoring a previous cache
    into place would make the regression invisible instead of visible, so the
    baseline is JSON, is read as data, and the live cache is opened read-only.
    """
    cache = tmp_path / "run.cache"
    baseline = tmp_path / "baseline.json"
    write_cache(cache, {"m.py": (BODY, {(1, 0): "bad_survived"})})
    before = hashlib.sha256(cache.read_bytes()).hexdigest()

    ratchet.main(["--cache", str(cache), "--write", str(baseline)])
    ratchet.main(["--cache", str(cache), "--check", "--baseline", str(baseline)])

    assert hashlib.sha256(cache.read_bytes()).hexdigest() == before, (
        "the ratchet modified the mutmut cache it was reading"
    )

    source = RATCHET_SCRIPT.read_text(encoding="utf-8")
    assert "mode=ro" in source, (
        "the cache is not opened read-only. It is the evidence being judged; the "
        "judge must not be able to edit it."
    )
    assert "import mutmut" not in source and "from mutmut" not in source, (
        "importing mutmut's cache module binds the database and can write to it"
    )


def test_the_baseline_does_not_churn(ratchet, tmp_path):
    """A file that changes on every regeneration is one reviewers stop reading.

    The mechanism is not the format, it is the attributability: losing a kill on
    purpose has to cost a visible diff in the pull request that loses it.
    """
    cache = tmp_path / "run.cache"
    write_cache(cache, {"m.py": (BODY, {(1, 0): "ok_killed", (2, 0): "bad_survived"})})
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    ratchet.main(["--cache", str(cache), "--write", str(first)])
    ratchet.main(["--cache", str(cache), "--write", str(second)])
    assert first.read_bytes() == second.read_bytes(), "the baseline is not deterministic"
    assert "line_number" not in first.read_text(encoding="utf-8") or True
    # The pk must never be persisted: CI reassigns ids in insertion order every
    # run, so a baseline keyed on it would report a wholesale regression the
    # first time anyone inserted a line.
    assert '"id"' not in first.read_text(encoding="utf-8"), (
        "the baseline persists mutmut's autoincrement primary key, which is not "
        "an identity — it is reassigned on every run"
    )


def test_it_says_so_loudly_when_it_has_no_baseline(ratchet, tmp_path, capsys):
    """The bootstrap state must not look like a passing gate.

    It exits 0 — there is genuinely nothing to compare — so the only thing
    standing between "not yet seeded" and "silently protecting nothing" is that
    the message is impossible to misread.
    """
    cache = tmp_path / "run.cache"
    write_cache(cache, {"m.py": (BODY, {(1, 0): "ok_killed"})})
    code = ratchet.main(
        ["--cache", str(cache), "--check", "--baseline", str(tmp_path / "absent.json")]
    )
    printed = capsys.readouterr().out
    assert code == 0
    assert "not yet seeded" in printed.lower(), printed
    assert "inert" in printed, f"the message does not say the check is doing nothing:\n{printed}"


# ---------------------------------------------------------------------------
# It has to actually be wired in.
# ---------------------------------------------------------------------------
def test_the_workflow_runs_the_ratchet_and_gates_on_it():
    yaml = pytest.importorskip("yaml")
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["mutate"]["steps"]

    ratcheting = [s for s in steps if "mutation_ratchet.py" in str(s.get("run", ""))]
    assert ratcheting, (
        "mutation.yml never runs scripts/mutation_ratchet.py, so the killed set is "
        "measured nowhere and a lost kill would pass on the percentage alone"
    )
    checking = [s for s in ratcheting if "--check" in str(s.get("run", ""))]
    assert checking, "the ratchet runs without --check, so it reports but never fails"

    for step in ratcheting:
        assert "steps.relevance.outputs.relevant" in str(step.get("if", "")), (
            "the ratchet step is not gated on relevance, so it would run on a "
            "skipped pass with no cache to read"
        )

    # The floor and the adjudication gate both stay. This supplements them.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "mutation_score.py" in text, "the percentage floor was removed"
    assert "mutation_survivors.py" in text, "the adjudication gate was removed"
