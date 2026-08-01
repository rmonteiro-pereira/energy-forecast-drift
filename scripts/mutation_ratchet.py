"""Ratchet the killed *set*, not the percentage.

The floor in `scripts/mutation_score.py` is a real gate and it is not enough.
Demonstrated rather than feared: a review deleted two assertions —
`tests/test_backtest_accounting.py:92-93`, the only lines in the repository that
read `overall["bias"]` — and two full mutmut passes said the suite was fine.

    the suite                       267 passed, green
    mutants                         exactly one kill lost, the bias formula
    mutation_survivors.py --check   exit 0, "Every surviving mutant is adjudicated"
    the floor                       315/474 = 66.5% >= 66, passes

Two causes, both measured:

  * **Quantisation.** One mutant is 0.21 points. A floor with headroom has room
    for deletions inside it; a floor without headroom fails on clock noise.
  * **Absorption.** 195 of 316 kills (62%) would land on an existing
    ACCEPTED/GAP adjudication rule if they regressed, and `--check` fails only on
    UNADJUDICATED, never on GAP. The same absorption had already hidden a real,
    shipped gap for months: `"rmse"` -> `"XXrmseXX"` survived every run because
    no test mentioned rmse.

So this compares *which mutants* were killed, not how many. Per-mutant
attribution, no quantisation slack, and the adjudication regexes stop being able
to decide the verdict.

It **supplements** `mutation_survivors.py --check`; it does not replace it. A
killed-set comparison is blind to a *new* survivor and to an *unclassified* one.
Both gates run.

---

Three things about mutmut 2.5.1 decide the implementation. All three were
established by reading `mutmut/cache.py` and diffing two real CI caches.

**1. The integer primary key is not an identity.** `Mutant` uses Pony's implicit
autoincrement `id` — the number `mutmut show <id>` takes. CI never restores the
cache, so every run rebuilds from scratch and assigns ids in insertion order.
Insert one line and every later id shifts. The pk is never persisted here.

**2. `(filename, line_text, index)` is not unique, and an occurrence ordinal does
not fix it.** Measured on the real cache: 474 mutants collapse to 446 keys — 21
keys colliding over 49 mutants, 2 of them mixing a kill with a survivor. `    )`
alone appears at seven different lines of `drift/detectors.py`. An ordinal is
unique but not *stable*: with lines `[a, ), b, ), c]` a mutant on the second `)`
has ordinal 1, and inserting another `)` above makes ordinal 1 name the **newly
inserted** line — silently transferring the old kill onto a different mutant.

So identity is migrated with `difflib.SequenceMatcher` over the line sequences,
exactly as `cache.py::update_line_numbers` does: migrate on `equal`, drop on
`replace`/`delete`. Aligning *sequences* rather than counting occurrences is what
makes duplicate lines tractable. A dropped identity is not a regression — an
edited line is a new mutant, and its predecessor's kill legitimately retires.

**3. The previous cache must never be restored into place.**
`cache.py::cached_mutation_status` returns `OK_KILLED` **without re-running**
whenever the mutant was previously killed, on the stated assumption that *"if a
mutant was killed, a change to the test suite will mean it's still killed."*
That assumption is precisely the attack above: restoring the cache would make the
regression invisible instead of visible. The baseline here is JSON, is read as
data, and is never written to `.mutmut-cache`.

---

`SequenceMatcher` still cannot disambiguate **identical lines**. Inserting a `)`
beside a `)` gives `[equal 0-2->0-2, insert 2-2->2-3, equal 2-3->3-4]`, and
which of the two identical lines is "the original" is not a question the text
can answer; `SequenceMatcher` picks one consistently but arbitrarily. That is
harmless when the statuses match and not harmless when they differ — 2 of the 21
collisions above. **This refuses rather than guesses.**

The refusal's scope is the **exchange region**: two copies of the same text
belong to one region unless a *matched* line of different text sits between
them. Matched lines are the anchors the alignment is pinned to; unmatched lines
— the insertions and deletions of the edit itself — pin nothing. Issue #21
originally scoped the refusal to runs of *adjacent* identical lines, and FH-20
closed the gap that scope left open: with `[def, L, L, return]` becoming
`[def, L, pass, L, L, return]`, `SequenceMatcher` calls lines 1-2 the insertion
and slides the old pair onto 3 and 4 — the old run maps contiguously onto a
same-length new run, so a shape-only disturbance test saw nothing, while the
surviving copy at line 1 was just as plausibly one of the originals. The
inserted `pass` was never aligned to anything, so it separates nothing: under
the region rule the three copies are one coin flip, and the identity is refused.

A contested identity — one whose region's alignment moved — is judged by its
**possible readings**: one per copy in the new region it could have aligned to,
plus retirement when the copy count dropped, the only case where the text itself
proves a copy went away. When every reading is harmless (`held`, `retired`,
`inconclusive`), the arbitrary choice cannot hide a lost kill, so the choice
stands — that is what keeps the 21 known collisions here adjudicable and the
gate passable. When every reading is the same failure, that failure is reported
as itself: a kill whose every candidate copy is alive is `regressed`, not
`ambiguous`, because no reading saves it. Only when the readings genuinely
disagree is the identity `ambiguous` — refused rather than guessed, to be
adjudicated by a human, exactly as an unclassified survivor is.

**What the region rule still cannot see, stated rather than discovered later.**
The anchors are single lines. A duplicated multi-line *block* — `[A, B]`
inserted beside an existing `[A, B]` — puts a matched `B` between the two copies
of `A`, so each copy sits in its own region and the same coin flip returns one
level up, at block granularity. And a region whose copies were all dropped by
the matcher retires without refusal, trusting that nothing corresponds —
including the popular lines autojunk declines to match, exactly as mutmut itself
drops them.

---

    uv run python scripts/mutation_ratchet.py --write .github/mutation-baseline.json
    uv run python scripts/mutation_ratchet.py --check

Adjudication is re-baselining: the baseline is committed, so losing a kill on
purpose costs a visible diff in the pull request that loses it. That is the whole
mechanism — not the file format, the attributability.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
from bisect import bisect_right
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / ".mutmut-cache"
BASELINE = REPO / ".github" / "mutation-baseline.json"
SCHEMA_VERSION = 1


def _score_module():
    """`mutation_score.py`, imported by path so the two cannot disagree.

    "Killed" must mean the same thing in the ratchet as in the score. Restating
    the set here is how it would stop meaning the same thing: `bad_timeout` was
    already counted as a kill once, and the fix has to hold in both places.
    """
    path = REPO / "scripts" / "mutation_score.py"
    spec = importlib.util.spec_from_file_location("mutation_score", path)
    if not (spec and spec.loader):  # pragma: no cover - only if the file is gone
        sys.exit(f"cannot import {path}, which defines what counts as a kill")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


_SCORE = _score_module()
#: `ok_killed` + `ok_suspicious`. Shared with the score, deliberately.
KILLED: set[str] = set(_SCORE.KILLED)
#: The one status meaning the mutant lived.
SURVIVED: str = _SCORE.SURVIVED
#: `bad_timeout`, `untested`, `skipped` — an absence of evidence. Counted here as
#: neither a kill nor a regression: a slow runner must not read as a weakened
#: suite, which is the mistake `KILLED` already made once.
UNRESOLVED: set[str] = set(_SCORE.UNRESOLVED)


# ---------------------------------------------------------------------------
# reading a run
# ---------------------------------------------------------------------------
def read_cache(cache: Path) -> dict[str, dict]:
    """`{filename: {"lines": [...], "mutants": {(line_number, index): status}}}`.

    Read-only, and over a copy of the schema rather than through mutmut's ORM:
    importing `mutmut.cache` binds the database and can write to it, and this
    must never be able to modify the run it is judging.
    """
    if not cache.exists():
        sys.exit(
            f"No {cache.name} found. This reports on a completed run; it does not "
            "perform one. Run `uv run --extra dev mutmut run` first."
        )
    conn = sqlite3.connect(f"file:{cache}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    files: dict[str, dict] = {}
    for row in conn.execute(
        "select sf.filename as filename, l.line_number as line_number, l.line as line "
        "from Line l join SourceFile sf on l.sourcefile = sf.id "
        "order by sf.filename, l.line_number"
    ):
        entry = files.setdefault(row["filename"], {"lines": [], "mutants": {}})
        entry["lines"].append(row["line"] or "")

    for row in conn.execute(
        # `index` is a SQL keyword; Pony names the column that anyway, so it has
        # to be quoted or sqlite rejects the statement.
        "select sf.filename as filename, l.line_number as line_number, "
        'm."index" as idx, m.status as status '
        "from Mutant m join Line l on m.line = l.id "
        "join SourceFile sf on l.sourcefile = sf.id"
    ):
        entry = files.setdefault(row["filename"], {"lines": [], "mutants": {}})
        entry["mutants"][(row["line_number"], row["idx"])] = row["status"]

    conn.close()
    if not files:
        sys.exit(f"{cache} holds no mutants — the run did not do anything.")
    return files


def build_baseline(run: dict[str, dict]) -> dict:
    """The JSON that gets committed. Only the kills are load-bearing.

    Deliberately deterministic and timestamp-free: the point of committing this
    is that a lost kill shows up as a reviewable diff, and a file that churns on
    every regeneration is a file reviewers stop reading.
    """
    files = {}
    for filename in sorted(run):
        entry = run[filename]
        files[filename] = {
            "lines": entry["lines"],
            "mutants": [
                [line_no, index, entry["mutants"][(line_no, index)]]
                for line_no, index in sorted(entry["mutants"])
            ],
        }
    return {"version": SCHEMA_VERSION, "files": files}


def load_baseline(path: Path) -> dict[str, dict] | None:
    """`None` when there is no baseline yet — the bootstrap state, not an error."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if version != SCHEMA_VERSION:
        sys.exit(
            f"{path} is schema version {version!r}, this script reads "
            f"{SCHEMA_VERSION}. Regenerate it with --write rather than guessing."
        )
    return {
        name: {
            "lines": entry["lines"],
            "mutants": {(line_no, index): status for line_no, index, status in entry["mutants"]},
        }
        for name, entry in data["files"].items()
    }


# ---------------------------------------------------------------------------
# migrating identity across an edit
# ---------------------------------------------------------------------------
def migrate(old_lines: list[str], new_lines: list[str]) -> dict[int, int]:
    """Old line index -> new line index, for the lines that survived unchanged.

    `cache.py::update_line_numbers` in miniature, and deliberately using the same
    defaults: `SequenceMatcher(a=..., b=...)` with autojunk left on, because
    mirroring mutmut's alignment matters more than any opinion about whether
    autojunk is a good idea on source text.

    Lines under `replace`/`delete` are absent from the result. That is the
    correct semantics rather than a limitation: an edited line is a new mutant,
    so the old kill retires instead of regressing.
    """
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, _j2 in SequenceMatcher(a=old_lines, b=new_lines).get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset] = j1 + offset
    return mapping


def exchange_groups(lines: list[str], matched: set[int]) -> dict[int, tuple[int, ...]]:
    """Line index -> every copy of that line's text it could be confused with.

    Two copies of the same text belong to one group unless a **matched** line of
    different text sits between them. Matched lines are the alignment's anchors
    — they were paired with a definite partner on the other side, so no copy can
    cross them without breaking the alignment. Unmatched lines pin nothing: they
    are the insertions and deletions of the edit itself, which is exactly what
    the run-scoped rule this replaces got wrong — `[L, pass, L]` with the `pass`
    freshly inserted is two runs but one coin flip, because the `pass` was never
    aligned to anything (FH-20).

    Singletons are in the map on purpose, for the same reason they always were:
    a line that is unique in the old file can still land beside a fresh
    identical copy in the new one, and that alignment is just as unforced.
    """
    anchors = sorted(matched)
    positions: dict[str, list[int]] = {}
    for number, text in enumerate(lines):
        positions.setdefault(text, []).append(number)

    groups: dict[int, tuple[int, ...]] = {}
    for copies in positions.values():
        group = [copies[0]]
        for previous, current in pairwise(copies):
            # Any matched line strictly between two consecutive copies has
            # different text — a copy between them would itself be in `copies`.
            cut = bisect_right(anchors, previous)
            if cut < len(anchors) and anchors[cut] < current:
                for line in group:
                    groups[line] = tuple(group)
                group = []
            group.append(current)
        for line in group:
            groups[line] = tuple(group)
    return groups


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------
#: Still killed. Nothing to say.
HELD = "held"
#: Killed before, alive now, on a line that did not change. The whole point.
REGRESSED = "regressed"
#: Killed before, and now neither killed nor survived — a timeout, an untested
#: mutant. Not a regression: that is the conservative direction, because a slow
#: runner must not be able to accuse a commit.
INCONCLUSIVE = "inconclusive"
#: Its line was edited or deleted, so the mutant no longer exists. Legitimate.
RETIRED = "retired"
#: Its line survived unchanged but mutmut generated no mutant there. Not
#: legitimate on its own — a kill vanishing without its line moving is exactly
#: the silent loss this exists to catch — but it is what a change of mutmut
#: version also looks like, so the message says so.
VANISHED = "vanished"
#: Landed among identical copies whose alignment moved and whose possible
#: readings disagree about the verdict. Refused rather than guessed.
AMBIGUOUS = "ambiguous"

#: The verdicts that fail the gate.
FAILING = {REGRESSED, VANISHED, AMBIGUOUS}
#: The verdicts that do not. A contested identity whose every reading is in this
#: set falls through to the alignment's own choice: the choice is arbitrary, but
#: no reading loses a kill, so refusing would only cry wolf.
HARMLESS = {HELD, RETIRED, INCONCLUSIVE}


def contested_identities(
    old: dict, new: dict, mapping: dict[int, int]
) -> dict[tuple[int, int], set[str]]:
    """`(old_line, index)` -> every verdict the identity could honestly receive.

    Decided per exchange group and per mutation index — never per line. Keying
    it by line puts every identity in a group of one, where nothing is ever
    contested.

    A group is **contested** when its alignment moved: some copy is unmatched,
    the copy count changed, or the images do not cover the new group exactly.
    When every copy is matched and the images are exactly the new group, any
    equally-sized alignment pairs the copies the same way, so nothing was
    guessed — an untouched file therefore produces no contested identity at all,
    which is what keeps the 21 known collisions in this repository adjudicable.

    For a contested group, which copy is which is precisely the unanswerable
    question, so no per-copy ordering information is used: every copy in the new
    group is a possible reading for every identity in the old one. Retirement is
    a possible reading only when the copy count dropped — that is the one case
    where the text itself proves some copy went away. Admitting a retirement
    reading the text cannot force would let every duplicated regression excuse
    itself as "my line was deleted", which is the silent-green direction this
    gate exists to close.
    """
    old_groups = exchange_groups(old["lines"], set(mapping))
    new_groups = exchange_groups(new["lines"], set(mapping.values()))
    contested: dict[tuple[int, int], set[str]] = {}

    for group in set(old_groups.values()):
        images = [mapping[line] for line in group if line in mapping]
        if not images:
            # Every copy went away. Nothing to attribute it to, and nothing to
            # guess between: retirement is the honest verdict.
            continue
        # Monotonicity puts all images inside one new group: a matched line of
        # different text between two images would have its partner between the
        # two old copies, which would have split the old group.
        new_group = new_groups[images[0]]
        if len(group) == len(new_group) and images == list(new_group):
            continue  # every copy is matched and pinned; the alignment is forced

        for index in {i for line, i in old["mutants"] if line in group}:
            possible: set[str] = set()
            for line in new_group:
                status = new["mutants"].get((line, index))
                if status is None:
                    possible.add(VANISHED)
                elif status in KILLED:
                    possible.add(HELD)
                elif status in UNRESOLVED:
                    possible.add(INCONCLUSIVE)
                else:
                    possible.add(REGRESSED)
            if len(group) > len(new_group):
                possible.add(RETIRED)
            for line in group:
                if (line, index) in old["mutants"]:
                    contested[(line, index)] = possible
    return contested


def compare(baseline: dict[str, dict], current: dict[str, dict]) -> list[dict]:
    """One record per mutant that was killed in the baseline."""
    findings: list[dict] = []

    for filename in sorted(baseline):
        old = baseline[filename]
        new = current.get(filename)
        killed_before = {key: status for key, status in old["mutants"].items() if status in KILLED}
        if new is None:
            # The file is gone from the run entirely — deleted, or dropped from
            # `paths_to_mutate`. Every kill in it retires; widening or narrowing
            # scope is a decision, and `test_the_targets_are_the_two_documented_ones`
            # is the guard for that, not this one.
            findings += [
                {
                    "file": filename,
                    "line": line,
                    "index": index,
                    "verdict": RETIRED,
                    "detail": "the file is no longer mutated",
                }
                for line, index in sorted(killed_before)
            ]
            continue

        mapping = migrate(old["lines"], new["lines"])
        contested = contested_identities(old, new, mapping)

        for line, index in sorted(killed_before):
            record = {"file": filename, "line": line, "index": index}
            new_line = mapping.get(line)

            # Judged before retirement, deliberately. When one of several
            # identical copies is deleted, `SequenceMatcher` drops one of them
            # arbitrarily — so "its line was deleted" is itself one of the
            # readings, and a real regression can hide inside a retirement.
            # An all-harmless reading set falls through instead: the choice is
            # still arbitrary, but no reading loses a kill, so nothing that
            # matters was guessed.
            possible = contested.get((line, index))
            if possible is not None and not possible <= HARMLESS:
                if possible == {REGRESSED}:
                    # Every copy it could have aligned to is alive. The
                    # alignment is ambiguous; the verdict is not — calling this
                    # `ambiguous` would let `ambiguous` stop meaning "a human
                    # could still find this harmless".
                    findings.append(
                        {
                            **record,
                            "verdict": REGRESSED,
                            "detail": (
                                "every identical copy it could have aligned to is "
                                "alive, so no reading of the alignment saves it"
                            ),
                        }
                    )
                elif possible == {VANISHED}:
                    findings.append(
                        {
                            **record,
                            "verdict": VANISHED,
                            "detail": (
                                "no identical copy it could have aligned to carries a "
                                f"mutant at index {index}, so no reading of the "
                                "alignment explains it"
                            ),
                        }
                    )
                else:
                    findings.append(
                        {
                            **record,
                            "verdict": AMBIGUOUS,
                            "detail": (
                                "it sits among identical copies of its line whose "
                                "alignment moved and whose possible readings disagree "
                                f"({', '.join(sorted(possible))}). Which copy is the "
                                "original is not a question the text can answer, so "
                                "the status was not transferred."
                            ),
                        }
                    )
                continue

            if new_line is None:
                findings.append(
                    {**record, "verdict": RETIRED, "detail": "its line was edited or deleted"}
                )
                continue

            status = new["mutants"].get((new_line, index))
            if status is None:
                findings.append(
                    {
                        **record,
                        "verdict": VANISHED,
                        "detail": (
                            f"line {new_line} is unchanged but carries no mutant at index "
                            f"{index}. A kill cannot disappear without its line moving — "
                            "unless mutmut's mutation operators changed, in which case "
                            "re-baseline in a commit that says so."
                        ),
                    }
                )
            elif status in KILLED:
                findings.append({**record, "verdict": HELD, "detail": status})
            elif status in UNRESOLVED:
                findings.append({**record, "verdict": INCONCLUSIVE, "detail": status})
            else:
                findings.append({**record, "verdict": REGRESSED, "detail": status})

    return findings


def new_kills(baseline: dict[str, dict], current: dict[str, dict]) -> int:
    """How many mutants are killed now that the baseline did not have killed.

    Reported, never gated on. A rising number is the reason to re-baseline; it is
    not evidence of anything by itself.
    """
    count = 0
    for filename, new in current.items():
        old = baseline.get(filename)
        if old is None:
            count += sum(1 for status in new["mutants"].values() if status in KILLED)
            continue
        mapping = migrate(old["lines"], new["lines"])
        was_killed = {
            (mapping[line], index)
            for (line, index), status in old["mutants"].items()
            if status in KILLED and line in mapping
        }
        count += sum(
            1
            for key, status in new["mutants"].items()
            if status in KILLED and key not in was_killed
        )
    return count


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def report(findings: list[dict], baseline: dict[str, dict], current: dict[str, dict]) -> str:
    counts = {
        verdict: sum(1 for f in findings if f["verdict"] == verdict)
        for verdict in (HELD, REGRESSED, INCONCLUSIVE, RETIRED, VANISHED, AMBIGUOUS)
    }
    lines = [
        "## Mutation ratchet — the killed set\n",
        f"{len(findings)} mutants were killed in the baseline.\n",
        "| Verdict | Mutants | |",
        "|---|---:|---|",
        f"| held | {counts[HELD]} | still killed |",
        f"| retired | {counts[RETIRED]} | their line was edited; not a regression |",
        f"| inconclusive | {counts[INCONCLUSIVE]} | timed out or untested; neither |",
        f"| **regressed** | **{counts[REGRESSED]}** | **killed before, alive now** |",
        f"| **vanished** | **{counts[VANISHED]}** | **gone, on an unchanged line** |",
        f"| **ambiguous** | **{counts[AMBIGUOUS]}** | **refused rather than guessed** |",
        f"\n{new_kills(baseline, current)} mutants are killed now that the baseline "
        "did not have killed. Re-baseline to bank them.\n",
    ]

    for verdict, heading in (
        (REGRESSED, "Regressions — a kill was lost"),
        (VANISHED, "Vanished — a kill disappeared without its line changing"),
        (AMBIGUOUS, "Ambiguous — needs a human"),
    ):
        offenders = [f for f in findings if f["verdict"] == verdict]
        if not offenders:
            continue
        lines.append(f"\n### {heading} — {len(offenders)}\n")
        for finding in offenders[:40]:
            lines.append(
                f"- `{finding['file']}` line {finding['line']} index "
                f"{finding['index']} — {finding['detail']}"
            )
        if len(offenders) > 40:
            lines.append(f"- …and {len(offenders) - 40} more")

    if counts[REGRESSED] or counts[VANISHED]:
        lines.append(
            "\n::error::A mutant that was killed is no longer killed. Some change "
            "made the tests weaker without making any of them fail — which is the "
            "one thing no other check in this repository can see. Restore the "
            "assertion, or regenerate `.github/mutation-baseline.json` in the same "
            "commit and say why in the message."
        )
    if counts[AMBIGUOUS]:
        lines.append(
            "\n::error::Some identities could not be migrated without guessing: they "
            "sit among identical copies of their line whose alignment moved and "
            "whose possible readings disagree. Which copy is the original is not "
            "decidable from the text, and a ratchet that guesses there will "
            "eventually accuse the wrong commit. Adjudicate by regenerating the "
            "baseline in a commit that says what happened."
        )
    if not (counts[REGRESSED] or counts[VANISHED] or counts[AMBIGUOUS]):
        lines.append("\nNo kill was lost.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        type=Path,
        nargs="?",
        const=BASELINE,
        help="write the baseline from the current cache and exit",
    )
    parser.add_argument(
        "--check", action="store_true", help="compare the current cache against the baseline"
    )
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--cache", type=Path, default=None)
    args = parser.parse_args(argv)

    cache = args.cache if args.cache is not None else CACHE
    run = read_cache(cache)

    if args.write is not None:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(
            json.dumps(build_baseline(run), indent=1, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        killed = sum(
            1 for entry in run.values() for status in entry["mutants"].values() if status in KILLED
        )
        print(f"Wrote {args.write} — {killed} killed mutants across {len(run)} files.")
        return 0

    if not args.check:
        parser.error("nothing to do: pass --check or --write")

    baseline = load_baseline(args.baseline)
    if baseline is None:
        # The bootstrap state. Loud, because a silently absent baseline is a gate
        # that reports green while protecting nothing — and the baseline has to
        # come from a run on the CI runner: the two platforms disagree by 1.7
        # points here, and a baseline measured on the wrong one would accuse the
        # first correct run of a regression it did not cause.
        try:
            shown = args.baseline.relative_to(REPO)
        except ValueError:  # a baseline outside the repo, i.e. a test or a probe
            shown = args.baseline
        print(
            "## Mutation ratchet — not yet seeded\n\n"
            f"`{shown}` does not exist, so there is no "
            "killed set to ratchet against and this check is inert.\n\n"
            "Seed it from a run on the CI runner — not a local one, because the "
            "platforms disagree by about 1.7 points and a baseline measured on the "
            "wrong one would accuse the first correct run of a regression it did "
            "not cause. The mutation workflow uploads a ready-made "
            "`mutation-baseline` artifact on every run; download it and commit it."
        )
        return 0

    findings = compare(baseline, run)
    print(report(findings, baseline, run))
    return 1 if any(f["verdict"] in FAILING for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
