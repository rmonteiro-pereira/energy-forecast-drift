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

**Add it to `ci.yml`, on every push.** Rejected. A full pass takes ~25 minutes —
the wrong trade on every push, and the kind of slow job people learn to skip.

**Amended 2026-07-31: it does now run in CI, on a schedule.** The original
wording ("not run in CI") was accurate but became a liability: a mutation score
quoted in a document, with nothing that ever re-runs it, is indistinguishable
from a number someone typed. `.github/workflows/mutation.yml` runs it weekly and
on `workflow_dispatch`, writes the score to the job summary, and fails only when
the score drops below a floor.

The floor matters. `mutmut run` exits non-zero whenever *any* mutant survives,
which is permanently true here and says nothing about whether things got worse —
so the verdict comes from `scripts/mutation_score.py`, not from mutmut's exit
code. Weakening a test is otherwise invisible, because a weaker test still
passes.

**Amended 2026-08-01: the schedule was the wrong primary trigger, and the floor
was set from a rounded number measured on the wrong platform.** Both were caught
before the first scheduled run ever fired, on a public repository.

*The trigger.* "Too slow for every push, so put it on a cron" does not follow.
Mutation testing measures the strength of the **test suite**, and a test suite
only ever changes in a commit — so a calendar trigger fires exactly when nothing
changed and stays silent when something did. That costs the two things this job
exists for:

- **Attribution.** A red Monday 04:40 has no culprit commit; it has a week of
  them. The floor's declared purpose is to catch *regression*, on the grounds
  that weakening a test is invisible because a weaker test still passes. A
  regression detector that detects without accusing is half a tool.
- **Latency.** A test weakened on Tuesday surfaces six days and twenty commits
  later, long after the change stopped being under review.

The fix is the one this ADR's own "What would reverse this" section already
named: **run it when the things it measures change.** The trigger is now
`pull_request`, narrowed by a `paths` filter to `drift/detectors.py`,
`models/backtest.py`, `tests/**` and the mutation tooling itself. Those PRs are a
minority, so the ~25 minutes are paid only where they can buy something — and the
"wrong cost on every push" objection above stops applying, because it is no
longer every push.

The cron stays, with the reason it actually has rather than the one it was given.
It catches change that **does not arrive in a commit**: a new release of a
dependency can alter behaviour under a suite nobody touched, and only elapsed
time reveals that. It complements the PR trigger; it was never a substitute for
it.

*The floor.* The floor was set to `65` by reading `docs/MUTATION-TESTING.md`'s
published **65.0%** — but that figure is `308/474 = 64.9789%` rounded for display,
and `scripts/mutation_score.py` compared the **unrounded** value. The gate would
therefore have failed on the very measurement that produced it, printing
"**65.0%**" in its own summary table three lines above "Mutation score 65.0% is
below the floor of 65.0%". It went unnoticed because the workflow had run exactly
once in its history, at a different floor.

Worse, the 65.0% was measured on Windows, where 9 mutants came back `untested`
and the score counts those as not-killed. The one Ubuntu run on record
(`3fc7274`) reported **no `untested` bucket at all** — 474 = 248 killed + 226
survived — so the CI score was expected to be higher than the published one. **A
floor derived from a rounded number measured on another platform is a coin
flip.** So the floor is now set from a `workflow_dispatch` run at the same commit
on the actual runner, with a deliberately low floor, and then fixed below what
that run measured. `tests/test_mutation_config.py` pins the 308/474 rounding case
so the report and the verdict can never disagree again.

**Shipping a mutation config that cannot run.** Rejected explicitly, because it
is a live failure mode: a sibling project was found shipping `paths_to_mutate`
aimed at directories that did not exist, with the CI job set to `if: false`. That
combination reports a perfect score over zero mutants behind a green tick — worse
than no mutation testing, because it converts an absence into a false claim of
rigour. `tests/test_mutation_config.py` asserts every mutated path exists and has
real code, every test file named in the runner exists, the runner actually
invokes pytest, the workflow has no `if: false` at job or step level, and it has
a trigger that can actually fire.

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
- A ~25-minute job (free Actions time on a public repo) on the minority of PRs
  that touch the mutated modules or the tests, plus one weekly run for dependency
  drift — and a floor that will need raising as the score improves, because a
  ratchet nobody tightens is just a number.
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

*This one already happened* — see the 2026-08-01 amendment. The prediction was
that once the survivor list stabilised, the right move would be to re-run only
when those two modules change rather than on a schedule. The reason it moved was
not the survivor list stabilising but attribution, and the schedule was kept for
dependency drift rather than dropped; the direction was right.

Conversely, if a real defect ever ships from a module *outside* this scope, that
is evidence the scope is too narrow — and the fix is to widen it to that module
rather than to add a broad, slow, repo-wide pass nobody waits for.
