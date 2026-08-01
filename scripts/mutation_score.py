"""Read the mutmut cache, report the score, and enforce a floor.

Committed rather than left in a scratch directory, because the number in
`docs/MUTATION-TESTING.md` is only worth something if anyone can regenerate it:

    uv run --extra dev mutmut run
    uv run python scripts/mutation_score.py --floor 50

Exits non-zero when the score falls below `--floor`, so the scheduled workflow
catches a regression in test strength -- which is otherwise invisible, because
weakening a test does not fail any test.

`mutmut run` itself exits non-zero whenever *any* mutant survives, which is
always true here and says nothing about whether things got worse. That is why
the workflow reads the score through this script instead of trusting mutmut's
exit code.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / ".mutmut-cache"

#: mutmut 2.x statuses that mean "the tests caught it".
#:
#: Read mutmut's own `ok_`/`bad_` prefix: `ok_` means the mutant was caught,
#: `bad_` means it was not — or that nobody can tell. This set had both members
#: wrong, in opposite directions. The evidence is in mutmut's own source,
#: `mutmut/__init__.py::run_mutation`:
#:
#:     except TimeoutError:
#:         return BAD_TIMEOUT      # the run was killed by the clock. Whether a
#:                                 # test would have failed is unknown. Counting
#:                                 # it as a kill credits the suite for a hang.
#:
#:     if not survived and time_elapsed > test_time_base + baseline * multiplier:
#:         return OK_SUSPICIOUS    # `not survived` — the tests DID fail, so the
#:                                 # mutant IS dead. It was merely slow.
#:
#: So the old set credited a hang and threw away a genuine, slow kill. On a
#: shared runner that is not a rounding error: the same code measured twice on
#: one machine gave 69.7% and 74.2% — 4.5 points of clock noise — against a
#: floor with about three mutants of headroom.
KILLED = {"ok_killed", "ok_suspicious"}
#: The one status that means the mutant lived: no test failed.
SURVIVED = "bad_survived"
#: Neither caught nor survived. `bad_timeout` belongs here and not in KILLED: it
#: is an absence of evidence, so it counts against the score exactly as
#: `untested` does — the conservative direction, and the same one the untested
#: disclosure in docs/MUTATION-TESTING.md resolves in.
UNRESOLVED = {"bad_timeout", "untested", "skipped"}


def rows() -> list[sqlite3.Row]:
    if not CACHE.exists():
        sys.exit(
            f"No {CACHE.name} found. Run `uv run --extra dev mutmut run` first — "
            "this script reports on a completed run, it does not perform one."
        )
    conn = sqlite3.connect(CACHE)
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        select sf.filename as filename,
               l.line_number as line_number,
               l.line        as source,
               m.status      as status
        from Mutant m
        join Line       l  on m.line = l.id
        join SourceFile sf on l.sourcefile = sf.id
        """
    ).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--floor",
        type=float,
        default=0.0,
        help="fail if the overall score falls below this percentage",
    )
    parser.add_argument(
        "--survivors",
        type=int,
        default=25,
        help="how many surviving source lines to list (0 for none)",
    )
    args = parser.parse_args()

    data = rows()
    if not data:
        sys.exit("The mutmut cache holds no mutants — the run did not do anything.")

    per_file: dict[str, Counter] = defaultdict(Counter)
    survivors: dict[str, dict[int, str]] = defaultdict(dict)
    for row in data:
        per_file[row["filename"]][row["status"]] += 1
        if row["status"] == SURVIVED:
            survivors[row["filename"]][row["line_number"]] = (row["source"] or "").strip()

    overall: Counter = Counter()
    lines = ["| File | Killed | Total | Score |", "|---|---:|---:|---:|"]
    for name, counts in sorted(per_file.items()):
        overall.update(counts)
        killed = sum(counts[s] for s in KILLED)
        total = sum(counts.values())
        lines.append(f"| `{name}` | {killed} | {total} | {100.0 * killed / total:.1f}% |")

    killed = sum(overall[s] for s in KILLED)
    total = sum(overall.values())
    score = 100.0 * killed / total
    # The floor is compared against the *reported* number, not the raw one.
    # This is not cosmetic: 308/474 is 64.9789%, which prints as "65.0%" — so a
    # floor of 65 read from the published figure failed on the very run that
    # produced it, and the summary said "65.0%" three lines above the error
    # saying 65.0% was below 65.0%. A gate whose verdict disagrees with its own
    # report is a gate nobody can act on. One decimal, one number, both uses.
    reported = round(score, 1)
    lines.append(f"| **Total** | **{killed}** | **{total}** | **{reported:.1f}%** |")

    print("## Mutation score\n")
    print("\n".join(lines))
    print(f"\nRaw statuses: {dict(overall)}")

    # A timeout is not a result, and it moves the score downward silently. Name
    # it, because "the score dropped" and "the runner was slow" need different
    # responses and the number alone cannot tell them apart.
    unresolved = {s: overall[s] for s in UNRESOLVED if overall[s]}
    if unresolved:
        print(
            f"\n> **{sum(unresolved.values())} mutants were neither killed nor survived** "
            f"({unresolved}). They count against the score, which is the conservative "
            "direction — but a run with timeouts in it is measuring the runner as much "
            "as the suite. Re-run before treating a drop as a regression."
        )

    if args.survivors:
        print(f"\n## Surviving mutants (first {args.survivors} lines per file)\n")
        for name in sorted(survivors):
            print(f"### `{name}` — {len(survivors[name])} surviving lines\n")
            print("```")
            for line_no in sorted(survivors[name])[: args.survivors]:
                print(f"L{line_no:<5} {survivors[name][line_no][:96]}")
            print("```\n")

    if reported < args.floor:
        print(
            f"\n::error::Mutation score {reported:.1f}% is below the floor of {args.floor:.1f}%. "
            "Some change made the tests weaker without making any of them fail."
        )
        return 1

    print(f"\nScore {reported:.1f}% meets the floor of {args.floor:.1f}%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
