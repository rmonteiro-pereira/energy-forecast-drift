"""Adjudicate every surviving mutant. An unclassified survivor is a failure.

A mutation score is only honest if the survivors have been *looked at*. The
failure mode this guards against is a report that lists hundreds of survivors and
decides nothing about any of them — the number looks rigorous, and nobody has
actually asked whether the tests should have caught them.

So every survivor must match exactly one rule below, and every rule carries a
written reason and a verdict:

    ACCEPTED  — the mutation cannot change observable behaviour that a test
                should reasonably assert. Killing it would mean asserting
                implementation detail.
    GAP       — the tests genuinely should have caught this and do not. Each of
                these is named individually in docs/MUTATION-TESTING.md.

`--check` exits non-zero if any survivor matches no rule, so a new survivor
cannot quietly join the pile unexamined.

    uv run python scripts/mutation_survivors.py            # the full table
    uv run python scripts/mutation_survivors.py --check    # CI gate
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / ".mutmut-cache"
SURVIVED = "bad_survived"

ACCEPTED = "ACCEPTED"
GAP = "GAP"


@dataclass(frozen=True)
class Rule:
    name: str
    verdict: str
    reason: str
    #: Matched against the *source line* the mutant was generated from.
    pattern: re.Pattern[str] | None = None
    #: Or matched against an exact (file, line, snippet) location. The snippet
    #: must appear in the source line, so a location whose line number drifted
    #: fails to match and its survivor comes back UNADJUDICATED — loudly.
    #: A bare (file, line) pair once kept matching after an edit shifted the
    #: file by +25 lines: three rules quietly unhooked and one GAP fell into a
    #: broad ACCEPTED pattern. Content has to agree with the coordinate now.
    locations: frozenset[tuple[str, int, str]] = frozenset()

    def matches(self, filename: str, line_no: int, source: str) -> bool:
        for loc_file, loc_line, snippet in self.locations:
            if filename == loc_file and line_no == loc_line and snippet in source:
                return True
        return bool(self.pattern and self.pattern.search(source))


# ---------------------------------------------------------------------------
# The named gaps come FIRST, so a genuine gap is never swallowed by a broad
# "it's just a string" rule that happens to also match the line.
# ---------------------------------------------------------------------------
RULES: list[Rule] = [
    # -----------------------------------------------------------------------
    # Found by auditing the *accepted* pile rather than the gap pile.
    #
    # `accepted:sort-or-selection-order` matches on `\bmax\(`, and that pattern
    # is too broad: it was swallowing `max(1, window_hours // 24)` and
    # `max(window_start, first_usable...)`, neither of which orders anything for
    # a human. The second decides *which folds the backtest runs on*. Calling
    # that presentation was the exact failure this file warns about one comment
    # below -- a broad rule quietly absorbing a real gap -- so it is named here,
    # ahead of the rule that was hiding it.
    # -----------------------------------------------------------------------
    Rule(
        "gap:fold-window-arithmetic",
        GAP,
        "Arithmetic that selects the evaluated window, not the reported order. "
        "`make_cutoffs`' `window_start`/`start` decide which folds the backtest "
        "scores, and `span_days` sets the rolling-error window; the tests assert "
        "fold counts for the default configuration but never pin these "
        "expressions, so a mutation shifts the evaluated period undetected. "
        "(The `window_start` half of the original gap is closed: its mutants "
        "are killed since the cutoff-hour move, so only `start` and `span_days` "
        "remain here.)",
        locations=frozenset(
            {
                ("models/backtest.py", 102, "max(window_start, first_usable"),
                ("drift/detectors.py", 354, "max(1, window_hours // 24)"),
            }
        ),
    ),
    # `gap:mape-formula-unpinned` used to live here, covering
    # models/backtest.py:155. It is gone because the gap is *closed*:
    # tests/test_backtest_accounting.py now pins MAPE to hand-computed values
    # (a flat 100 MWh series mispredicted by 10 must give exactly 10%), which
    # kills all three mutants. The rule is removed rather than kept as a trophy —
    # if the test were reverted the mutants would come back UNADJUDICATED and
    # fail --check, which is the behaviour we want.
    # -----------------------------------------------------------------------
    # Mutants that are ACCEPTED because they are *provably equivalent*, not
    # because asserting them would be inconvenient. Each carries the reachability
    # argument, because "equivalent" without one is just a nicer word for
    # unexamined. Every one was predicted to survive before the run that
    # confirmed it did; the other nineteen named gaps were killed and their rules
    # are gone, so a regression brings the mutant back UNADJUDICATED and fails
    # `--check` rather than landing back on a comfortable label.
    # -----------------------------------------------------------------------
    Rule(
        "accepted:equivalent-unreachable-get-default",
        ACCEPTED,
        "`rollup.get('columns_scored', 0)` -> `..., 1)`. The default is dead "
        "code: `_section_from_columns` returns `columns_scored` on both of its "
        "branches -- 0 on the nothing-eligible path and `len(scored)` on the "
        "other -- so the key is always present and the fallback is never "
        "evaluated. No input can distinguish the two defaults.",
        locations=frozenset({("drift/detectors.py", 210, 'rollup.get("columns_scored", 0)')}),
    ),
    Rule(
        "accepted:equivalent-first-increment-from-zero",
        ACCEPTED,
        "`skipped += 1` -> `skipped = 1` in the no-history branch. The two differ "
        "only when `skipped` is already non-zero on entry, and it cannot be: "
        "cutoffs ascend, `start >= series.min()` always holds, so at most the "
        "very first cutoff has empty history and it is reached on iteration one "
        "with `skipped == 0`. The sibling `-= 1` and `+= 2` mutants at this line "
        "are killed by the exact-count assertion; only this one is equivalent.",
        locations=frozenset({("models/backtest.py", 144, "skipped += 1")}),
    ),
    Rule(
        "accepted:equivalent-every-boundary",
        ACCEPTED,
        "`every > 1` -> `every >= 1` in `markdown_table`'s row filter. Equivalent "
        "by cases: with `every == 1` the mutated branch filters on "
        "`horizon_h % 1 == 0`, which keeps every row, so the rendered string is "
        "byte-identical to the else branch; with `every > 1` both versions take "
        "the same branch. The five sibling mutants at this line are killed by "
        "the `every=6`/`every=2` tests in tests/test_backtest.py; this boundary "
        "alone has no observable side.",
        locations=frozenset({("models/backtest.py", 230, "if every > 1 else by_horizon")}),
    ),
    # -----------------------------------------------------------------------
    # Accepted categories.
    # -----------------------------------------------------------------------
    Rule(
        "accepted:equivalent-single-column-branch",
        ACCEPTED,
        "`if len(scored) == 1` is an *equivalent* mutant, provable by cases: with "
        "one scored column the share is 0.0 or 1.0, and the share ladder below "
        "reaches the same verdict for all three severities (ALERT via "
        "share >= alert; WARN via `or warning`; OK via the else). The branch is a "
        "readability shortcut, not a behavioural fork.",
        locations=frozenset({("drift/detectors.py", 161, "if len(scored) == 1")}),
    ),
    Rule(
        "accepted:redundant-payload-label",
        ACCEPTED,
        '`drift_type="feature"` and friends. `run_all` already keys the four '
        "sections by those exact names, so the label inside each section is a "
        "duplicate of the key a consumer indexes by. Asserting it twice would "
        "pin the duplication, not the behaviour.",
        pattern=re.compile(r"drift_type\s*="),
    ),
    Rule(
        "accepted:delegation-to-a-directly-tested-callee",
        ACCEPTED,
        "A call straight through to `_section_from_columns`, which has its own "
        "boundary tests covering every severity path. Mutating the call site "
        "either raises or reproduces what the callee's tests already pin.",
        pattern=re.compile(r"=\s*_section_from_columns\("),
    ),
    Rule(
        "accepted:artifact-detail-toggle",
        ACCEPTED,
        "`with_bins=` controls whether per-bin PSI detail is included in the "
        "artifact. Both settings produce a valid artifact; the flag changes "
        "verbosity, and the schema test asserts the keys that must be present "
        "regardless.",
        pattern=re.compile(r"with_bins\s*="),
    ),
    Rule(
        "accepted:empty-window-sentinel",
        ACCEPTED,
        "The all-None dict returned for an empty scoring window. Its only "
        "consumer is the insufficient-data guard, which is itself tested; the "
        "individual sentinel values are never read as numbers.",
        locations=frozenset({("drift/detectors.py", 315, '"mae": None, "mape_pct": None')}),
    ),
    # `accepted:table-rendering` used to live here, covering the row-selection
    # and line-joining mutants of `markdown_table` at models/backtest.py 205/215.
    # It is gone because "presentation only" was doing the work a test should do:
    # six of its seven mutants are now killed by the `every=6`/`every=2` and
    # pipe-delimiter tests in tests/test_backtest.py, and the seventh — the
    # `every >= 1` boundary — is genuinely equivalent and argued above under
    # `accepted:equivalent-every-boundary`. If those tests were reverted the
    # mutants would come back UNADJUDICATED and fail --check.
    Rule(
        "accepted:syntax-continuation",
        ACCEPTED,
        "A closing bracket or continuation line carrying no logic of its own. "
        "mutmut attributes some mutants to these lines; there is nothing on them "
        "for a test to assert.",
        pattern=re.compile(r"^\s*[)\]}]+,?\s*$"),
    ),
    Rule(
        "accepted:human-readable-text",
        ACCEPTED,
        "The mutation changes a string a human reads — a summary, a note, a log "
        "message, an f-string. Asserting exact wording makes every copy edit a "
        "test failure while protecting nothing: the artifact schema is asserted "
        "elsewhere, the prose is not load-bearing.",
        pattern=re.compile(
            r'^\s*(f?["\'])'  # a bare string literal line
            r'|^\s*\+?\s*\(?f["\']'  # a concatenated f-string
            r'|^\s*(summary|note|reason|detail)\s*=\s*f?["\']'  # assigned message
            r'|^\s*else\s+f?["\']'  # the else arm of a ternary message
        ),
    ),
    Rule(
        "accepted:dict-key-or-literal-field",
        ACCEPTED,
        "A dict key or a literal value in an artifact payload. The keys that "
        "matter are asserted by tests/test_artifacts.py against the published "
        "files; mutating the literal here is caught there or nowhere, and "
        "duplicating that assertion per-line would be noise.",
        pattern=re.compile(r'^\s*"[\w.\- ]+"\s*:'),
    ),
    Rule(
        "accepted:module-constant",
        ACCEPTED,
        "A module-level constant whose value is a default, not an invariant "
        "(DEFAULT_WEEKS, DEFAULT_CUTOFF_HOUR, an enum-ish string). Changing it "
        "changes configuration, which the threshold tests already parametrise.",
        pattern=re.compile(r"^[A-Z][A-Z0-9_]*\s*[:=]"),
    ),
    Rule(
        "accepted:dataclass-field-default",
        ACCEPTED,
        "A dataclass field default (`field(default_factory=...)`, `= 0`). The "
        "constructed values are asserted by the tests that build these objects.",
        pattern=re.compile(r":\s*[\w\[\], .|]+\s*=\s*(field\(|0\b|\[\]|None\b|False\b|True\b)"),
    ),
    Rule(
        "accepted:keyword-default-argument",
        ACCEPTED,
        "A default value in a function signature. Every caller in this codebase "
        "passes the argument explicitly, so the default is documentation.",
        pattern=re.compile(r"^\s*\w+\s*:\s*[\w\[\], .|]+\s*=\s*\S"),
    ),
    Rule(
        "accepted:rounding-precision",
        ACCEPTED,
        "The number of decimal places in a `round(...)` on a reported figure. "
        "Reporting 6 places instead of 4 is not a defect, and pinning it would "
        "assert formatting rather than behaviour.",
        pattern=re.compile(r"round\("),
    ),
    Rule(
        "accepted:none-guard-on-optional-report-field",
        ACCEPTED,
        "An `x is not None` guard around an optional *reported* value. Both "
        "branches are covered by the insufficient-data tests; the mutation "
        "swaps which of two already-tested paths is taken.",
        pattern=re.compile(r"\bif\s+\w[\w\[\]'\"]*\s+is\s+(not\s+)?None\b|\bis\s+not\s+None\b"),
    ),
    Rule(
        "accepted:severity-derivation-restated",
        ACCEPTED,
        "`severity is not Severity.OK` restated into a `drift_detected` boolean. "
        "The severity itself is pinned by the boundary tests; this line only "
        "mirrors it into the payload.",
        pattern=re.compile(r"is not Severity\.OK"),
    ),
    Rule(
        "accepted:sort-or-selection-order",
        ACCEPTED,
        "A sort key or a max/idxmax selection that decides presentation order. "
        "The set of items is asserted; their order in the report is not a "
        "correctness property.",
        pattern=re.compile(r"\.sort\(|sorted\(|\bmax\(|idxmax\(|key=lambda"),
    ),
    Rule(
        "accepted:comprehension-filter-restating-a-tested-rule",
        ACCEPTED,
        "A comprehension filter restating a rule asserted directly elsewhere — "
        "the deterministic-column exclusion and the insufficient-data exclusion "
        "both have dedicated tests in tests/test_drift_boundaries.py.",
        pattern=re.compile(r"for c in columns|c\.get\(\"deterministic\"|insufficient_data"),
    ),
    Rule(
        "accepted:dataframe-plumbing",
        ACCEPTED,
        "Dataframe assembly — concat/assign/groupby arguments, column plumbing. "
        "A mutation here either raises immediately (caught) or produces the same "
        "frame; the frame's contents are asserted by the tests that consume it.",
        pattern=re.compile(
            r"pd\.(concat|DataFrame|DatetimeIndex|Timedelta|Timestamp)|"
            r"\.assign\(|\.groupby\(|\.reset_index\(|\.rolling\(|ignore_index|"
            r"\.itertuples\(|\.dropna\(|\.loc\[|\.iloc\["
        ),
    ),
    Rule(
        "accepted:strict-zip-pairing",
        ACCEPTED,
        "`zip(horizons, target_times, strict=True)`. Dropping `strict` is the "
        "only available mutation, and it cannot change behaviour here: the two "
        "sequences are built from the same `horizons` tuple one line apart, so "
        "they are equal length by construction. `strict=True` documents that "
        "invariant rather than enforcing a reachable one.",
        locations=frozenset(
            {("models/backtest.py", 159, "zip(horizons, target_times, strict=True)")}
        ),
    ),
    Rule(
        "accepted:local-alias-or-unpack",
        ACCEPTED,
        "A local binding or tuple unpack immediately consumed by the next line, "
        "which is itself covered. Mutating it changes a name, not behaviour.",
        pattern=re.compile(r"^\s*\w+(\s*,\s*\w+)*\s*=\s*[\w.\[\]\"'()]+\s*$"),
    ),
]


def survivors() -> list[tuple[str, int, str, int]]:
    """(filename, line_number, source, mutant_count) for every surviving line."""
    if not CACHE.exists():
        sys.exit(f"No {CACHE.name}. Run `uv run --extra dev mutmut run` first.")
    conn = sqlite3.connect(CACHE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select sf.filename as filename, l.line_number as line_number,
               l.line as source, count(*) as n
        from Mutant m
        join Line l on m.line = l.id
        join SourceFile sf on l.sourcefile = sf.id
        where m.status = ?
        group by sf.filename, l.line_number, l.line
        order by sf.filename, l.line_number
        """,
        (SURVIVED,),
    ).fetchall()
    return [
        (r["filename"].replace("\\", "/"), r["line_number"], (r["source"] or "").strip(), r["n"])
        for r in rows
    ]


def classify(filename: str, line_no: int, source: str) -> Rule | None:
    for rule in RULES:
        if rule.matches(filename, line_no, source):
            return rule
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="exit non-zero on any unadjudicated survivor"
    )
    parser.add_argument("--markdown", action="store_true", help="emit the full table as markdown")
    args = parser.parse_args()

    rows = survivors()
    if not rows:
        print("No surviving mutants.")
        return 0

    by_rule: dict[str, list] = defaultdict(list)
    unclassified: list[tuple[str, int, str, int]] = []
    mutants = Counter()

    for filename, line_no, source, n in rows:
        rule = classify(filename, line_no, source)
        if rule is None:
            unclassified.append((filename, line_no, source, n))
            continue
        by_rule[rule.name].append((filename, line_no, source, n))
        mutants[rule.verdict] += n

    total_mutants = sum(n for *_, n in rows)
    total_lines = len(rows)

    print("## Survivor adjudication\n")
    print(f"{total_mutants} surviving mutants across {total_lines} source lines.\n")
    print("| Verdict | Rule | Lines | Mutants |")
    print("|---|---|---:|---:|")
    for rule in RULES:
        hits = by_rule.get(rule.name)
        if not hits:
            continue
        print(f"| {rule.verdict} | `{rule.name}` | {len(hits)} | {sum(n for *_, n in hits)} |")
    print(f"| | **total** | **{total_lines}** | **{total_mutants}** |")

    print(
        f"\n**{mutants[GAP]} mutants are real gaps. {mutants[ACCEPTED]} are accepted.** "
        f"{100.0 * mutants[GAP] / total_mutants:.1f}% of survivors are gaps.\n"
    )

    print("### Reasons\n")
    for rule in RULES:
        if rule.name in by_rule:
            print(f"- **`{rule.name}`** ({rule.verdict}) — {rule.reason}")

    if args.markdown:
        print("\n### Every surviving line\n")
        print("| File | Line | Mutants | Verdict | Rule | Source |")
        print("|---|---:|---:|---|---|---|")
        for filename, line_no, source, n in rows:
            rule = classify(filename, line_no, source)
            name = rule.name if rule else "UNADJUDICATED"
            verdict = rule.verdict if rule else "???"
            escaped = source.replace("|", "\\|")[:70]
            print(f"| `{filename}` | {line_no} | {n} | {verdict} | `{name}` | `{escaped}` |")

    if unclassified:
        print(f"\n## {len(unclassified)} UNADJUDICATED survivors\n")
        for filename, line_no, source, n in unclassified:
            print(f"  {filename}:{line_no}  x{n}  {source[:90]}")
        print(
            "\n::error::Some surviving mutants match no rule in scripts/mutation_survivors.py. "
            "Each must be either killed by a test or given a written reason — an undecided "
            "survivor is how a mutation report becomes decoration."
        )
        return 1

    print("\nEvery surviving mutant is adjudicated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
