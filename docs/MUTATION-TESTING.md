# Mutation testing

> **The headline number is 61.2%.** It is published here
> because a measured mediocre score with the survivors listed is worth more than
> a flattering one — and because finding out *which* assertions were missing
> already produced a real fix.

A green suite says the tests ran. It does not say they would have noticed if the
code were wrong. Mutation testing answers the second question: change the code in
a small, plausible way, and see whether any test fails. A mutant that survives is
a change nobody was checking for.

Scope, and why these two files, is in
[ADR 0007](adr/0007-mutation-testing-scoped-not-global.md).

## This actually runs — it is not a config sitting in a file

`.github/workflows/mutation.yml` runs it **weekly and on demand**, writes the
score into the job summary, and fails when it drops below a floor. There is no
`if: false`, and `tests/test_mutation_config.py` (15 tests) asserts that the
mutated paths exist and contain real code, that every test file named in the
runner exists, that the runner invokes pytest, that no step is disabled, and
that the workflow has a trigger that can fire.

That guard exists because the opposite is a real failure mode: a config aimed at
directories that do not exist, behind a job set to `if: false`, reports a perfect
score over zero mutants and shows a green tick. That is worse than no mutation
testing — it turns an absence into a false claim of rigour.

The verdict comes from the score, not from mutmut's exit code: `mutmut run`
exits non-zero whenever *any* mutant survives, which is permanently true here.

## How to run it

```bash
uv run --extra dev mutmut run                            # ~28 min for 474 mutants
uv run python scripts/mutation_score.py --floor 61       # the number below
uv run python scripts/mutation_survivors.py --check      # every survivor judged
```

`scripts/mutation_score.py` is committed, not scratch tooling — the figure in
this document is only worth something if someone else can regenerate it.

> **⚠️ `mutmut` 2.x rewrites the source file in place while it runs** and restores
> it when it finishes. An interrupted run can leave `drift/detectors.py` mutated
> with a `.bak` beside it. **Check `git status` before committing after a run.**
> The version is pinned `>=2.4,<3` because mutmut 3.x refuses to run natively on
> Windows; on Linux/macOS 3.x is the better tool.

## The score

Measured on commit `3dd8e20` + the boundary tests, 2026-07-31.

| File | Killed | Total | Score |
|---|---:|---:|---:|
| `drift/detectors.py` | 198 | 342 | **57.9%** |
| `models/backtest.py` | 92 | 132 | **69.7%** |
| **Total** | **290** | **474** | **61.2%** |

### Before and after the boundary tests

The first run is reported too, because the improvement is the interesting part.

| Run | Killed / total | Score | What changed |
|---|---:|---:|---|
| 1 — as the suite stood | 223 / 470 | 47.4% | — |
| 2 — after `tests/test_drift_boundaries.py` | 248 / 474 | 52.3% | 21 new boundary tests |
| 3 — after closing three named gaps | 290 / 474 | **61.2%** | 18 tests over `drift_timeline`, the MAPE formula and fold accounting |

Across the three runs `drift/detectors.py` went **42.0% -> 48.8% -> 57.9%** and
`models/backtest.py` **61.4% -> 61.4% -> 69.7%**. The mutant count rose from 470
to 474 because the artifact fix described below added four mutable lines.

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

## Every one of the 184 survivors is adjudicated

Not summarised — **adjudicated**. Each surviving mutant matches exactly one rule
in [`scripts/mutation_survivors.py`](../scripts/mutation_survivors.py), and each
rule carries a verdict and a written reason. `--check` **fails** when a survivor
matches no rule, and that gate runs in the mutation workflow, so a new survivor
cannot quietly join the pile unexamined.

```bash
uv run python scripts/mutation_survivors.py            # the full table
uv run python scripts/mutation_survivors.py --check    # the CI gate
```

**184 mutants across 141 source lines. 21 are real gaps (11.4%); 163 are
accepted.**

> **The gap count has moved twice, in both directions, and both moves matter.**
> An early draft put it at 14 — a guess from eyeballing categories, too
> flattering by nearly three times. Adjudicating every survivor individually
> raised it to 38. Then three of those gaps were *closed* with real tests, taking
> it to 21 and the score from 52.3% to 61.2%. Up because the method got honest;
> down because the tests got better. Only the second kind is worth celebrating.
>
> **`gap:mape-formula-unpinned` is gone entirely** — `tests/test_backtest_accounting.py`
> now pins MAPE to hand-computed values (a flat 100 MWh series mispredicted by
> exactly 10 must give exactly 10%), killing all three mutants. The rule was
> deleted rather than kept as a trophy: revert the test and those mutants come
> back **unadjudicated** and fail `--check`, which is the behaviour we want.

### The gaps — 21 mutants the tests should have caught

| Rule | Lines | Mutants | Why it survives |
|---|---:|---:|---|
| `gap:drift-timeline-untested` | 2 | 2 | `drift_timeline` is asserted for shape, never content: which rows fall in which trailing window, which features are eligible, and the below-`min_samples` path are all unpinned. Largest single gap. |
| `gap:skipped-fold-accounting-weakly-asserted` | 3 | 5 | The only assertion is `skipped_folds >= 1` — incrementing by two, or skipping a different fold, still passes. Existence is checked; correctness is not. |
| `gap:feature-drift-insufficient-branch` | 2 | 6 | The "no column was eligible" branch of `feature_drift` is unreached: the test calls `_section_from_columns` directly and never goes through the detector. |
| `gap:compound-or-short-circuits` | 1 | 2 | Three-way `or` in the WARN branch; the other disjuncts short-circuit and mask a mutation of any one. |
| `gap:degenerate-input-guards` | 2 | 2 | `make_cutoffs` guards reachable only with a series shorter than any fixture builds. |
| `gap:ks-alpha-boundary` | 1 | 1 | KS exercised at 10× either side of alpha, never *at* alpha, so `<` and `<=` never disagree. |
| `gap:min-samples-boundary` | 1 | 1 | `min_samples` tested well inside both regions, never at exactly 200. |
| `gap:performance-insufficient-compound-guard` | 1 | 1 | Exercised only via an empty reference window; the other two disjuncts are masked. |
| `gap:mape-zero-guard` | 1 | 1 | Never exercised with an actual of exactly `0.0`. |

Two of those are worth reading twice, because they are cases where a test exists
and is **too weak to be worth its green tick**: `skipped_folds >= 1` passes on a
counter that increments by two, and `mape_pct == approx(0.0)` passes on any
formula at all when the forecast is perfect. Mutation testing is the only thing
in this repository that could have found either.

### The accepted survivors — 188 mutants, and why each is not a defect

| Rule | Lines | Mutants | Reason |
|---|---:|---:|---|
| `accepted:human-readable-text` | 83 | 110 | Summaries, notes, log messages, f-strings. Asserting exact wording breaks on every copy edit and protects nothing; the artifact *schema* is asserted separately. |
| `accepted:dataframe-plumbing` | 11 | 15 | concat/assign/groupby arguments. A mutation either raises immediately or produces the same frame, whose contents are asserted by the tests that consume it. |
| `accepted:sort-or-selection-order` | 7 | 9 | Sort keys and `idxmax` selection deciding presentation order. The *set* is asserted; the order in a report is not a correctness property. |
| `accepted:table-rendering` | 2 | 7 | Markdown row selection and line joining. Presentation only. |
| `accepted:dataclass-field-default` | 6 | 7 | Field defaults; the constructed values are asserted by the tests that build these objects. |
| `accepted:module-constant` | 4 | 6 | Configuration defaults, already parametrised by the threshold tests. |
| `accepted:redundant-payload-label` | 5 | 5 | `drift_type="feature"` — `run_all` already keys the sections by those exact names, so the label duplicates the key a consumer indexes by. |
| `accepted:empty-window-sentinel` | 1 | 5 | The all-`None` dict for an empty window; its only consumer is the insufficient-data guard, which is tested. |
| `accepted:none-guard-on-optional-report-field` | 4 | 4 | Both branches covered; the mutation swaps which already-tested path is taken. |
| `accepted:local-alias-or-unpack` | 4 | 4 | A binding consumed by the next line, which is itself covered. |
| `accepted:comprehension-filter-restating-a-tested-rule` | 3 | 3 | The deterministic-column and insufficient-data exclusions each have dedicated tests. |
| `accepted:delegation-to-a-directly-tested-callee` | 3 | 3 | Straight-through calls to `_section_from_columns`, which has its own boundary tests. |
| `accepted:artifact-detail-toggle` | 3 | 3 | `with_bins=` changes verbosity; both settings produce a valid artifact. |
| `accepted:syntax-continuation` | 3 | 3 | Closing brackets carrying no logic. |
| `accepted:keyword-default-argument` | 2 | 2 | Every caller passes the argument explicitly. |
| `accepted:equivalent-single-column-branch` | 1 | 1 | **Provably equivalent**: with one scored column the share is 0.0 or 1.0 and the ladder below reaches the same verdict for all three severities. A readability shortcut, not a fork. |
| `accepted:strict-zip-pairing` | 1 | 1 | The two sequences are built from the same tuple one line apart, so `strict=True` documents an invariant rather than enforcing a reachable one. |

## What this does *not* say

- It covers **two files**. The other ~4,500 lines are unmeasured. This is not a
  repo-wide quality figure and is not presented as one.
- 52.3% is a **low score**. Roughly half the small changes you could make to
  those two files would go unnoticed by the suite. The mitigating detail is
  *which* half: 110 of the 226 surviving mutants are prose, and the comparisons
  that drive the alarm are now pinned. The mitigating detail is not an excuse —
  38 survivors are genuine gaps and they are listed above by name.
- It says nothing about whether the *thresholds themselves* are right. Mutation
  testing checks that the code does what the tests say; whether PSI > 0.2 is the
  correct place to alert on real PJM demand is an empirical question that needs
  real data.

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
