# Mutation testing

> **The headline number is 66.7%**, measured on the CI runner
> ([run 30680545024](https://github.com/rmonteiro-pereira/energy-forecast-drift/actions/runs/30680545024),
> `ubuntu-latest`, commit `41e5d02`). The same commit scores **65.0%** on Windows,
> and both numbers are below. It is published here because a measured mediocre
> score with the survivors listed is worth more than a flattering one — and
> because finding out *which* assertions were missing already produced a real fix.

A green suite says the tests ran. It does not say they would have noticed if the
code were wrong. Mutation testing answers the second question: change the code in
a small, plausible way, and see whether any test fails. A mutant that survives is
a change nobody was checking for.

Scope, and why these two files, is in
[ADR 0007](adr/0007-mutation-testing-scoped-not-global.md).

## This actually runs — it is not a config sitting in a file

`.github/workflows/mutation.yml` runs it **on every pull request that touches
something able to move the score** — the two mutated modules, the seven test files
that drive them, or the mutation tooling — plus **weekly** for dependency drift
and **on demand**. It writes the score into the job summary and fails when the
score drops below a floor. There is no `if: false`, and
`tests/test_mutation_config.py` asserts that the mutated paths exist and contain
real code, that every test file named in the runner exists, that the runner
invokes pytest, that no step is disabled, that the workflow has a trigger that
can fire, **that the pull-request `paths` filter names every test the runner
drives**, and **that the floor is compared against the score this document
publishes**.

> **The trigger used to be the schedule alone, and that was the wrong choice.**
> Mutation testing measures the strength of a *test suite*, and a suite only
> changes in a commit — so a calendar trigger fires precisely when nothing
> changed and stays silent when something did. A red Monday 04:40 has no culprit
> commit; it has a week of them. The full argument, and why the cron is *kept*
> for the one job it is genuinely the only trigger for — a dependency release
> changing behaviour under a suite nobody touched — is in the 2026-08-01
> amendment to [ADR 0007](adr/0007-mutation-testing-scoped-not-global.md).

That guard exists because the opposite is a real failure mode: a config aimed at
directories that do not exist, behind a job set to `if: false`, reports a perfect
score over zero mutants and shows a green tick. That is worse than no mutation
testing — it turns an absence into a false claim of rigour.

The verdict comes from the score, not from mutmut's exit code: `mutmut run`
exits non-zero whenever *any* mutant survives, which is permanently true here.

## How to run it

```bash
uv run --extra dev mutmut run                            # ~28 min for 474 mutants
uv run python scripts/mutation_score.py --floor 66       # the CI floor
uv run python scripts/mutation_survivors.py --check      # every survivor judged
```

> **On Windows, expect 65.0% and not 66.7%, and that is not a regression.** See
> [the platform note](#the-same-commit-scores-differently-on-windows) below before
> concluding the score dropped.

`scripts/mutation_score.py` is committed, not scratch tooling — the figure in
this document is only worth something if someone else can regenerate it.

> **⚠️ `mutmut` 2.x rewrites the source file in place while it runs** and restores
> it when it finishes. An interrupted run can leave `drift/detectors.py` mutated
> with a `.bak` beside it. **Check `git status` before committing after a run.**
> The version is pinned `>=2.4,<3` because mutmut 3.x refuses to run natively on
> Windows; on Linux/macOS 3.x is the better tool.

## The score

**The measurement the floor is set from**, on the CI runner —
[run 30680545024](https://github.com/rmonteiro-pereira/energy-forecast-drift/actions/runs/30680545024),
`ubuntu-latest`, commit `41e5d02`, 2026-08-01:

| File | Killed | Total | Score |
|---|---:|---:|---:|
| `drift/detectors.py` | 217 | 342 | **63.5%** |
| `models/backtest.py` | 99 | 132 | **75.0%** |
| **Total** | **316** | **474** | **66.7%** |

The floor is **66**.

### The same commit scores differently on Windows

The local run of the same code, on Windows, 2026-07-31, gave `drift/detectors.py`
**209 / 342** and `models/backtest.py` **99 / 132** — **308 / 474 = 65.0%**.

**65.0% locally, 66.7% in CI, same code.** The difference is entirely the nine
`untested` mutants described [below](#every-one-of-the-158-survivors-is-adjudicated):
Windows leaves nine mutants untested and the score counts them as not-killed;
this runner leaves **none** (`Raw statuses: {'ok_killed': 316, 'bad_survived':
158}` — no `untested` key at all). Of the nine, eight resolve as killed and one
as a survivor, which is exactly `308 + 8 = 316` and `157 + 1 = 158`.

That gap of 1.7 points is why the floor is set from a CI run rather than a local
one. The floor before this was `65`, taken from the rounded **65.0%** above —
a number that was both measured on the wrong platform *and* rounded up from
`308/474 = 64.9789%`, which the gate then compared unrounded. It would have
failed on its own measurement, and it had never run at that value: the workflow
had one execution in its whole history, at floor 50. Both halves are fixed —
`scripts/mutation_score.py` now compares the number it prints, and
`tests/test_mutation_config.py` pins the 308/474 case so the report and the
verdict cannot disagree again.

### Every run, because the trajectory is the interesting part

| Run | Killed / total | Score | What changed |
|---|---:|---:|---|
| 1 — as the suite stood | 223 / 470 | 47.4% | — |
| 2 — after `tests/test_drift_boundaries.py` | 248 / 474 | 52.3% | 21 new boundary tests |
| 3 — after closing three named gaps | 290 / 474 | 61.2% | 18 tests over `drift_timeline`, the MAPE formula and fold accounting |
| 4 — after killing 19 of the 21 named gaps | 308 / 474 | **65.0%** | 13 tests written against the *mutant diffs*, not the prose descriptions of them |
| 5 — **the same code, on the CI runner** | 316 / 474 | **66.7%** | *no test changed.* Runs 1–4 were local, on Windows; this one is `ubuntu-latest`, and the nine `untested` mutants resolve there |

Runs 1–4 are local (Windows). Across them `drift/detectors.py` went
**42.0% → 48.8% → 57.9% → 61.1%** and `models/backtest.py`
**61.4% → 61.4% → 69.7% → 75.0%**. The mutant count rose from 470 to 474 because
the artifact fix described below added four mutable lines.

**Run 5 is the platform, not progress**, and it is listed as a run precisely so
nobody reads the jump as a test improvement. It is also the run the floor is set
from, because it is the environment the gate executes in.

Run 4 is the one worth reading the method for. Every previous round wrote tests
from the *description* of a gap; this one pulled `mutmut show <id>` for all 21 and
wrote each test against the actual mutation. That is why the two survivors are
survivors: they were predicted equivalent from the diff **before** the run, and
the run agreed.

> **Two portability findings from run 4**, both Windows-only and neither
> affecting CI (which is Ubuntu): `mutmut run` crashes at startup on a cp1252
> console because its banner contains an emoji — `PYTHONIOENCODING=utf-8` fixes
> it — and **killing a run mid-mutant leaves the mutation on disk.** The second
> one is why the warning below is in bold; it was caught here by `git status`
> before anything was committed.

## What the first run found

The survivors clustered somewhere specific and alarming: **the threshold
comparisons themselves.** Mutating any of

```python
if mae_ratio >= thresholds.mae_degradation_alert:      # -> `>`
elif share  >= thresholds.drifted_share_alert:         # -> `>`
ks_significant = ks.p_value < thresholds.ks_p_alert    # -> `<=`
```

left the entire suite green. Every existing test drove those comparisons from
well inside one region or the other, so the boundary — the single input where
`>=` and `>` disagree — was never exercised. **A detector whose alert threshold
is off by one comparison looks fine for months and then does not fire.**

`tests/test_drift_boundaries.py` now pins each documented threshold just below,
exactly on, and just above.

### Two real findings that came out of writing those tests

**1. The default MAE thresholds are not exactly reachable in floating point.**
`mae_ratio` is `current / reference - 1.0`, and for the default warn threshold of
0.15 the nearest double is *below* it: `1150.0 / 1000.0 - 1.0 == 0.14999999999999991`.
So "exactly at the threshold" is not a state the shipped configuration can be in,
and the `>=`/`>` mutant is *equivalent* for the default bands. The test therefore
pins the comparison on 0.25, which **is** exactly representable
(`1.25 - 1.0 == 0.25`). The MAPE ladder does not have this problem — it is a
subtraction, and `2.5 - 2.0 == 0.5` holds exactly.

**2. A genuine inconsistency in the artifact, now fixed.** When *every* column was
excluded — all deterministic, or all below `min_samples` — `_section_from_columns`
returned early with a key set that omitted `columns_excluded_deterministic`. A
consumer reading the artifact got different keys depending on whether anything
happened to be eligible, and "everything was excluded as deterministic" is
precisely when a reader most wants to know which columns those were. Both
branches now report it.

## Every one of the 158 survivors is adjudicated

Not summarised — **adjudicated**. Each surviving mutant matches exactly one rule
in [`scripts/mutation_survivors.py`](../scripts/mutation_survivors.py), and each
rule carries a verdict and a written reason. `--check` **fails** when a survivor
matches no rule, and that gate runs in the mutation workflow, so a new survivor
cannot quietly join the pile unexamined.

```bash
uv run python scripts/mutation_survivors.py            # the full table
uv run python scripts/mutation_survivors.py --check    # the CI gate
```

**158 mutants across 124 source lines. 4 are real gaps (2.5%); 154 are
accepted.**

> **0 mutants mutmut never tested** on the CI runner: `316 + 158 = 474` exactly,
> and the raw statuses carry no `untested` key at all. **The local Windows run
> leaves nine**, and the score counts those as not-killed — `308 + 157 = 465`,
> not 474. Every one of the nine is on a syntax-continuation line (a bare `)` or
> `]`) where mutmut attributes a mutant it then cannot meaningfully run; on Linux
> eight of them are killed and one survives, which is precisely the 1.7-point gap
> between the two platforms.
>
> They are named rather than quietly dropped from the denominator, in either
> direction: counting them as failures makes the headline *worse* than the tested
> evidence supports, which is the direction an unexplained hole in the arithmetic
> should always be resolved. `tests/test_mutation_config.py` fails if this
> disclosure disappears, and the arithmetic in that test uses the number.

> **The gap count has now moved four times, in both directions.** An early draft
> put it at 14 — a guess from eyeballing categories, too flattering by nearly
> three times. Adjudicating every survivor individually raised it to 38. Closing
> three of those with real tests took it to 21 and the score from 52.3% to 61.2%.
> This round killed **nineteen of the remaining twenty-one**, taking the score to
> **65.0%** — and then *raised* the gap count again by finding a new one in the
> accepted pile. Up because the method got honest; down because the tests got
> better. Only the second kind is worth celebrating.
>
> **Nineteen gap rules are gone entirely, not kept as trophies.** Revert any of
> those tests and the mutants come back **unadjudicated** and fail `--check`,
> which is the behaviour we want. The remaining two of the old twenty-one turned
> out to be *provably equivalent* and are now argued as such below.

### The gaps — 4 mutants the tests should have caught

| Rule | Lines | Mutants | Why it survives |
|---|---:|---:|---|
| `gap:fold-window-arithmetic` | 3 | 4 | `make_cutoffs`' `window_start`/`start` decide **which folds the backtest scores**, and `span_days` sets the rolling-error window. The tests assert fold counts for the default configuration but never pin these expressions, so a mutation shifts the evaluated period undetected. |

**This one was found by auditing the *accepted* pile, not the gap pile** — which
is the part worth reading. `accepted:sort-or-selection-order` matches on
`\bmax\(`, and that pattern was quietly absorbing `max(window_start,
first_usable…)`: not an ordering decision at all, but the expression that chooses
which folds get evaluated. A broad rule swallowing a real gap is the exact
failure this file's own comment warns about, and it happened anyway. It is named
here, ahead of the rule that was hiding it.

The lesson generalises: **the dangerous half of a survivor list is the half
already marked fine.** A gap you have named is being worked on; a gap sitting
inside a category you stopped reading is not.

### Two survivors that are equivalent, with the argument

These were the last two of the old twenty-one. Both were **predicted to survive
before the run that confirmed it**, which is the only reason the label is worth
anything — "equivalent" asserted after the fact is just a nicer word for
unexamined.

| Rule | Mutant | Why no input can distinguish it |
|---|---|---|
| `accepted:equivalent-unreachable-get-default` | `rollup.get("columns_scored", 0)` → `…, 1)` | The default is dead code. `_section_from_columns` returns `columns_scored` on **both** branches — `0` on the nothing-eligible path, `len(scored)` on the other — so the key is always present and the fallback never evaluates. |
| `accepted:equivalent-first-increment-from-zero` | `skipped += 1` → `skipped = 1` | They differ only if `skipped` is already non-zero, and it cannot be: cutoffs ascend and `start >= series.min()` always holds, so at most the *first* cutoff has empty history, reached on iteration one with `skipped == 0`. The sibling `-= 1` and `+= 2` mutants on that line **are** killed, by the exact-count assertion. |

### The accepted survivors — 154 mutants, and why each is not a defect

| Rule | Lines | Mutants | Reason |
|---|---:|---:|---|
| `accepted:human-readable-text` | 75 | 96 | Summaries, notes, log messages, f-strings. Asserting exact wording breaks on every copy edit and protects nothing; the artifact *schema* is asserted separately. **This is the only row that differs between platforms** — the one Windows-`untested` mutant that survives on Linux lands here. |
| `accepted:sort-or-selection-order` | 2 | 3 | Sort keys and `idxmax` selection deciding presentation order. The *set* is asserted; the order in a report is not a correctness property. **Narrowed this round** — it used to cover 8 mutants, four of which were `make_cutoffs` arithmetic and are now `gap:fold-window-arithmetic`. |
| `accepted:equivalent-unreachable-get-default` | 1 | 1 | **Provably equivalent** — argued in full above. The `.get` default is unreachable because both return paths always set the key. |
| `accepted:equivalent-first-increment-from-zero` | 1 | 1 | **Provably equivalent** — argued in full above. `skipped` is provably 0 when that branch is reached, so `= 1` and `+= 1` cannot differ. |
| `accepted:table-rendering` | 2 | 7 | Markdown row selection and line joining. Presentation only. |
| `accepted:dataframe-plumbing` | 6 | 6 | concat/assign/groupby arguments. A mutation either raises immediately or produces the same frame, whose contents are asserted by the tests that consume it. |
| `accepted:dataclass-field-default` | 5 | 6 | Field defaults; the constructed values are asserted by the tests that build these objects. |
| `accepted:module-constant` | 4 | 6 | Configuration defaults, already parametrised by the threshold tests. |
| `accepted:redundant-payload-label` | 5 | 5 | `drift_type="feature"` — `run_all` already keys the sections by those exact names, so the label duplicates the key a consumer indexes by. |
| `accepted:empty-window-sentinel` | 1 | 4 | The all-`None` dict for an empty window; its only consumer is the insufficient-data guard, which is tested. |
| `accepted:none-guard-on-optional-report-field` | 4 | 4 | Both branches covered; the mutation swaps which already-tested path is taken. |
| `accepted:comprehension-filter-restating-a-tested-rule` | 3 | 3 | The deterministic-column and insufficient-data exclusions each have dedicated tests. |
| `accepted:delegation-to-a-directly-tested-callee` | 3 | 3 | Straight-through calls to `_section_from_columns`, which has its own boundary tests. |
| `accepted:artifact-detail-toggle` | 3 | 3 | `with_bins=` changes verbosity; both settings produce a valid artifact. |
| `accepted:keyword-default-argument` | 2 | 2 | Every caller passes the argument explicitly. |
| `accepted:local-alias-or-unpack` | 2 | 2 | A binding consumed by the next line, which is itself covered. |
| `accepted:equivalent-single-column-branch` | 1 | 1 | **Provably equivalent**: with one scored column the share is 0.0 or 1.0 and the ladder below reaches the same verdict for all three severities. A readability shortcut, not a fork. |
| `accepted:strict-zip-pairing` | 1 | 1 | The two sequences are built from the same tuple one line apart, so `strict=True` documents an invariant rather than enforcing a reachable one. |

`accepted:syntax-continuation` is still defined but now matches **nothing** — its
mutant was killed as collateral. The rule stays because the category will recur;
the row is dropped because a count of zero in a table of survivors is noise.

## What this does *not* say

- It covers **two files**. The other ~4,500 lines are unmeasured. This is not a
  repo-wide quality figure and is not presented as one.
- 66.7% is still a **modest score**. Roughly a third of the small changes you
  could make to those two files would go unnoticed by the suite. The mitigating
  detail is *which* third: 96 of the 158 surviving mutants are prose, and every
  comparison that drives the alarm is now pinned. The mitigating detail is not an
  excuse — 4 survivors are genuine gaps and they are listed above by name.
- **It says nothing about whether the thresholds themselves are right.** Mutation
  testing checks that the code does what the tests say. Whether PSI > 0.2 is the
  right place to alert is a different question, and it now has its own answer:
  [`docs/DRIFT-EVALUATION.md`](DRIFT-EVALUATION.md) runs the shipped detectors
  against real weather and finds the thresholds **fire on two of three control
  windows where nothing changed**. A 67% mutation score and a false-positive-prone
  threshold are entirely compatible — the code correctly implements a rule that is
  itself miscalibrated, which is exactly why both measurements exist.

## The one thing worth taking away

The single most important guard in this repository is
`models/backtest.py:51` —

```python
return series[series.index < cutoff]
```

— the strict inequality that keeps the walk-forward backtest from reading the
future. **Its mutants were killed.** `<` → `<=`, `<` → `>`, and the rest all fail
the suite. The leakage claim the whole project rests on is the part that is
actually held down by tests, and mutation testing is how that stopped being an
assumption.
