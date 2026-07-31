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
KILLED = {"ok_killed", "bad_timeout"}
#: ...and the one that means they did not.
SURVIVED = "bad_survived"


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
    lines.append(f"| **Total** | **{killed}** | **{total}** | **{score:.1f}%** |")

    print("## Mutation score\n")
    print("\n".join(lines))
    print(f"\nRaw statuses: {dict(overall)}")

    if args.survivors:
        print(f"\n## Surviving mutants (first {args.survivors} lines per file)\n")
        for name in sorted(survivors):
            print(f"### `{name}` — {len(survivors[name])} surviving lines\n")
            print("```")
            for line_no in sorted(survivors[name])[: args.survivors]:
                print(f"L{line_no:<5} {survivors[name][line_no][:96]}")
            print("```\n")

    if score < args.floor:
        print(
            f"\n::error::Mutation score {score:.1f}% is below the floor of {args.floor:.1f}%. "
            "Some change made the tests weaker without making any of them fail."
        )
        return 1

    print(f"\nScore {score:.1f}% meets the floor of {args.floor:.1f}%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
