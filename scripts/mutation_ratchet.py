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

`SequenceMatcher` still cannot disambiguate a run of **adjacent identical
lines**. Inserting a `)` beside a `)` gives
`[equal 0-2->0-2, insert 2-2->2-3, equal 2-3->3-4]`, and which of the two
identical lines is "the original" is not a question the text can answer;
`SequenceMatcher` picks one consistently but arbitrarily. That is harmless when
the statuses match and not harmless when they differ — 2 of the 21 collisions
above. **This refuses rather than guesses**: identities landing in a disturbed
run of identical lines with non-uniform statuses are reported `ambiguous` and
fail, to be adjudicated by a human, exactly as an unclassified survivor is.

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
from difflib import SequenceMatcher
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


def identical_runs(lines: list[str]) -> list[tuple[int, int]]:
    """Maximal runs of two or more consecutive identical lines, as `[start, end)`."""
    runs: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(lines) + 1):
        if index == len(lines) or lines[index] != lines[start]:
            if index - start >= 2:
                runs.append((start, index))
            start = index
    return runs


def disturbed_lines(
    old_lines: list[str], new_lines: list[str], mapping: dict[int, int]
) -> dict[int, tuple[int, int]]:
    """New-line index -> the identical-line run it sits in, for disturbed runs only.

    The run bounds, not just the line, because the ambiguity is *between the
    lines of a run*: two identities landing anywhere in the same run at the same
    mutation index are the ones whose statuses have to agree before either can
    transfer. Keying that check by line instead of by run puts every identity in
    a group of one, where every set of statuses is trivially uniform and nothing
    is ever refused.

    A run is *disturbed* when a line was inserted into or deleted from it, or when
    the old lines landing in it are no longer consecutive. That is exactly the
    situation where `SequenceMatcher` had to pick which of several identical lines
    is "the original" — a question the text cannot answer.

    An untouched run is not disturbed, so an unchanged file produces no ambiguity
    at all. Refusing on every duplicate line regardless would make the 21 known
    collisions in this repository permanently unadjudicable, which is a gate
    nobody can get past rather than a gate that bites.
    """
    inverse = {new: old for old, new in mapping.items()}
    disturbed: dict[int, tuple[int, int]] = {}
    for start, end in identical_runs(new_lines):
        landed = sorted(inverse[j] for j in range(start, end) if j in inverse)
        consecutive = bool(landed) and landed == list(range(landed[0], landed[0] + len(landed)))
        if len(landed) != end - start or not consecutive:
            for line in range(start, end):
                disturbed[line] = (start, end)
    return disturbed


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
#: Landed in a disturbed run of identical lines carrying more than one status.
#: Refused rather than guessed.
AMBIGUOUS = "ambiguous"

#: The verdicts that fail the gate.
FAILING = {REGRESSED, VANISHED, AMBIGUOUS}


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
        disturbed = disturbed_lines(old["lines"], new["lines"], mapping)

        # Which baseline identities land in each disturbed run, per mutation
        # index — the group whose statuses have to agree before any of them can
        # transfer. Keyed by the run, not by the line: the whole question is
        # which line of the run an identity belongs to.
        grouped: dict[tuple[tuple[int, int], int], list[str]] = {}
        for (line, index), status in old["mutants"].items():
            new_line = mapping.get(line)
            if new_line is not None and new_line in disturbed:
                grouped.setdefault((disturbed[new_line], index), []).append(status)

        for line, index in sorted(killed_before):
            record = {"file": filename, "line": line, "index": index}
            new_line = mapping.get(line)

            if new_line is None:
                findings.append(
                    {**record, "verdict": RETIRED, "detail": "its line was edited or deleted"}
                )
                continue

            if new_line in disturbed:
                siblings = grouped.get((disturbed[new_line], index), [])
                # Only refuse when the guess would actually matter. Identical
                # lines produce identical mutations, so swapping two identities
                # that agree swaps nothing observable.
                if len(set(siblings)) > 1:
                    findings.append(
                        {
                            **record,
                            "verdict": AMBIGUOUS,
                            "detail": (
                                f"line {new_line} sits in a run of identical lines whose "
                                f"alignment moved, carrying more than one status "
                                f"({sorted(set(siblings))}). Which line is the original "
                                "is not a question the text can answer."
                            ),
                        }
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
            "landed in a run of adjacent identical lines whose alignment moved and "
            "whose statuses disagree. Which line is the original is not decidable "
            "from the text, and a ratchet that guesses there will eventually accuse "
            "the wrong commit. Adjudicate by regenerating the baseline in a commit "
            "that says what happened."
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
