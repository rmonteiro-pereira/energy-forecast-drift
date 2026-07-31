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
    #: Or matched against an exact (file, line) location, for the named gaps.
    locations: frozenset[tuple[str, int]] = frozenset()

    def matches(self, filename: str, line_no: int, source: str) -> bool:
        if self.locations and (filename, line_no) in self.locations:
            return True
        return bool(self.pattern and self.pattern.search(source))


# ---------------------------------------------------------------------------
# The named gaps come FIRST, so a genuine gap is never swallowed by a broad
# "it's just a string" rule that happens to also match the line.
# ---------------------------------------------------------------------------
RULES: list[Rule] = [
    Rule(
        "gap:ks-alpha-boundary",
        GAP,
        "The KS significance comparison is exercised at 10x either side of alpha "
        "but never AT alpha, so `<` and `<=` never disagree. Killable with a test "
        "that pins p_value exactly at ks_p_alert.",
        locations=frozenset({("drift/detectors.py", 103)}),
    ),
    Rule(
        "gap:min-samples-boundary",
        GAP,
        "`min_samples` is tested well inside both regions, never at exactly 200. "
        "Same shape as the alpha boundary.",
        locations=frozenset({("drift/detectors.py", 107)}),
    ),
    Rule(
        "gap:compound-or-short-circuits",
        GAP,
        "A three-way `or` in the WARN branch. The other disjuncts short-circuit, "
        "so mutating any one of them is masked. Killable only with inputs "
        "contrived to make exactly one disjunct decide the outcome.",
        locations=frozenset({("drift/detectors.py", 165)}),
    ),
    Rule(
        "gap:drift-timeline-untested",
        GAP,
        "`drift_timeline` is asserted for shape, never for content: which rows "
        "fall in which trailing window, which features are eligible, and what "
        "happens below `min_samples` are all unpinned. The largest single gap.",
        locations=frozenset(
            {
                ("drift/detectors.py", 483),
                ("drift/detectors.py", 490),
                ("drift/detectors.py", 491),
                ("drift/detectors.py", 492),
                ("drift/detectors.py", 502),
            }
        ),
    ),
    Rule(
        "gap:feature-drift-insufficient-branch",
        GAP,
        "The 'no column was eligible' branch of `feature_drift` is unreached: "
        "`test_columns_below_the_minimum_sample_size_are_not_scored` calls "
        "`_section_from_columns` directly and never goes through the detector, "
        "so the summary it produces is untested.",
        locations=frozenset({("drift/detectors.py", 210), ("drift/detectors.py", 211)}),
    ),
    Rule(
        "gap:performance-insufficient-compound-guard",
        GAP,
        "`if not reference['n'] or not current['n'] or not reference['mae']` is "
        "exercised only via an empty reference window, so the other two "
        "disjuncts are masked by short-circuiting.",
        locations=frozenset({("drift/detectors.py", 373)}),
    ),
    Rule(
        "gap:mape-formula-unpinned",
        GAP,
        "The MAPE formula `(abs_error / |actual|) * 100` survives mutation "
        "because the only assertion on it is `mape_pct == approx(0.0)` for a "
        "perfect forecast — which holds for any scaling of a zero numerator. "
        "Needs a case with a known non-zero error.",
        locations=frozenset({("models/backtest.py", 155)}),
    ),
    Rule(
        "gap:skipped-fold-accounting-weakly-asserted",
        GAP,
        "`skipped += 1` and the surrounding `continue`s survive because the only "
        "assertion is `skipped_folds >= 1` — incrementing by two, or skipping a "
        "different fold, still passes. The count is checked for existence, not "
        "for correctness.",
        locations=frozenset(
            {
                ("models/backtest.py", 119),
                ("models/backtest.py", 120),
                ("models/backtest.py", 139),
                ("models/backtest.py", 144),
                ("models/backtest.py", 150),
            }
        ),
    ),
    Rule(
        "gap:mape-zero-guard",
        GAP,
        "The MAPE zero-guard is never exercised with an actual of exactly 0.0, "
        "so the `!= 0.0` comparison is unpinned.",
        locations=frozenset({("models/backtest.py", 200)}),
    ),
    Rule(
        "gap:degenerate-input-guards",
        GAP,
        "Degenerate-input guards in `make_cutoffs`, reachable only with a series "
        "shorter than any fixture the tests build.",
        locations=frozenset({("models/backtest.py", 66), ("models/backtest.py", 79)}),
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
        locations=frozenset({("drift/detectors.py", 161)}),
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
        locations=frozenset({("drift/detectors.py", 315)}),
    ),
    Rule(
        "accepted:table-rendering",
        ACCEPTED,
        "Markdown table rendering for the human-readable report — row selection "
        "and line joining. Presentation only; the numbers it formats come from "
        "the artifact, which is asserted directly.",
        locations=frozenset({("models/backtest.py", 205), ("models/backtest.py", 215)}),
    ),
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
        locations=frozenset({("models/backtest.py", 134)}),
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
