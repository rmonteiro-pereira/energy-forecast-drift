# 0007 — Mutation-test the two places a green suite would be most misleading

**Status:** Accepted · **Date:** 2026-07

## Context

The suite is green and reasonably large, and neither of those facts says whether
the assertions are load-bearing. Line coverage is worse than useless here: a test
that calls `feature_drift(...)` and asserts the result *has* a `severity` key
executes every line of the detector and would keep passing if the comparison
inside it were inverted.

Two areas make that gap dangerous rather than merely untidy:

- **`drift/detectors.py`** — a comparison flipped from `>=` to `>`, or a
  threshold read from the wrong side, is the difference between an alarm that
  fires and one that silently never does. The fixture is quiet enough that
  ordinary assertions pass either way.
- **`models/backtest.py`** — the walk-forward split. `index < cutoff` becoming
  `index <= cutoff` is a one-character temporal leak that makes every metric
  look *better* and breaks no visible behaviour. It is the exact defect the
  project's central claim ("no temporal leakage, enforced in four places")
  depends on not having.

## Decision

Run `mutmut` against exactly those two modules, driven by the tests that cover
them, and **publish the real score with the surviving mutants listed
individually** in [`docs/MUTATION-TESTING.md`](../MUTATION-TESTING.md).

Configuration lives in `pyproject.toml` under `[tool.mutmut]`.

The reporting rule matters as much as the run: **a measured low score with an
honest survivor list beats a flattering number.** Each survivor is either fixed
with a new test or recorded with the reason it is not worth killing. An
unexplained survivor is a finding, not a footnote.

## Rejected alternatives

**Mutation-test the whole codebase.** Rejected on cost and signal. The full
package is ~4,500 lines; at a few seconds per mutant that is many hours per run,
and most of it is dataframe plumbing and I/O where a surviving mutant usually
means "this line is glue", not "this assertion is weak". Scoping concentrates the
effort where a false green is actually expensive.

**Add it to CI.** Rejected. A full pass takes tens of minutes — the wrong trade
on every push, and the kind of slow job people learn to skip. It is run
deliberately and the score is committed, so the number is reviewable without
being in the critical path. If it were ever gated, it would need to be a
scheduled job against a fixed mutant set, not a per-PR check.

**Use line coverage as the quality signal instead.** Rejected as insufficient,
per the context above. Coverage answers "was this executed"; mutation answers
"would anything have noticed if it were wrong". They are not substitutes, and
this project's central claims are of the second kind.

**Chase 100%.** Rejected. Equivalent mutants exist (changes that cannot alter
observable behaviour), and some survivors are genuinely not worth a test —
mutating a log message, or a tie-break that no input can reach. Forcing those to
zero produces tests that assert implementation details and then break on every
refactor. The target is "every survivor is understood", not "the number is 100".

## Consequences

- One more dev dependency, and a run that is slow enough to be deliberate.
- **`mutmut` 2.x rewrites the source file in place while it runs** and restores
  it afterwards. An interrupted run can leave `drift/detectors.py` mutated with a
  `.bak` beside it. Anyone running it must check `git status` before committing.
  This is a real footgun and is called out in `docs/MUTATION-TESTING.md`.
- mutmut 3.x refuses to run natively on Windows, so the version is pinned to
  `>=2.4,<3`. On Linux/macOS 3.x would work and is the better tool.
- The score is a point-in-time measurement of two files, and says nothing about
  the rest of the suite. It is reported that way rather than as a repo-wide
  quality figure.

## What would reverse this

If the survivor list stabilises at a small, fully-explained set, the marginal
value of re-running drops and the right move is to re-run it only when those two
modules change, rather than on a schedule.

Conversely, if a real defect ever ships from a module *outside* this scope, that
is evidence the scope is too narrow — and the fix is to widen it to that module
rather than to add a broad, slow, repo-wide pass nobody waits for.
