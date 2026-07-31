# Mutation testing

> **The headline number is 52.3%, and that is not good.** It is published here
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
uv run --extra dev mutmut run                            # ~25 min for 474 mutants
uv run python scripts/mutation_score.py --floor 50       # the number below
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
| `drift/detectors.py` | 167 | 342 | **48.8%** |
| `models/backtest.py` | 81 | 132 | **61.4%** |
| **Total** | **248** | **474** | **52.3%** |

### Before and after the boundary tests

The first run is reported too, because the improvement is the interesting part.

| Run | Killed / total | Score | What changed |
|---|---:|---:|---|
| 1 — as the suite stood | 223 / 470 | 47.4% | — |
| 2 — after `tests/test_drift_boundaries.py` | 248 / 474 | **52.3%** | 21 new boundary tests |

`drift/detectors.py` went **42.0% → 48.8%**. `models/backtest.py` is unchanged at
**61.4%**, because the new tests targeted the detectors only — stated rather than
averaged away. The mutant count rose from 470 to 474 because the fix described
below added four mutable lines.

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

## The 226 survivors, honestly

Classified by what the mutated line actually is:

| Kind | Survivor lines | Worth killing? |
|---|---:|---|
| Strings, log messages, dict keys, `description`/`note` prose | 120 | **No.** Asserting exact wording makes tests break on every copy edit and protects nothing. |
| Comparisons and branches | 13 | **Some — listed below.** |
| Arithmetic and `round(x, n)` precision | 4 | Mostly no. Rounding a reported figure to 6 places instead of 4 is not a defect. |
| Other (defaults, sort keys, dataclass fields) | 26 | Mixed. |

### The survivors that are real gaps

Named individually rather than summarised, because these are the ones a reader
should hold against the suite:

| Location | Line | Why it survives |
|---|---|---|
| `detectors.py:103` | `ks.p_value < thresholds.ks_p_alert` | The KS test is exercised at 10× either side of alpha, never at exactly alpha, so `<` and `<=` never disagree. |
| `detectors.py:107` | `min(ref_n, cur_n) < thresholds.min_samples` | Same: `min_samples` is tested well inside both regions, never at exactly 200. |
| `detectors.py:165` | `elif alerting or share >= warn or warning:` | A three-way `or`. The other disjuncts short-circuit, masking a mutation of any one of them. Genuinely hard to kill without contrived inputs. |
| `detectors.py:490` | `frame[(frame["day"] <= day) & (frame["day"] > day - span)]` | **7 mutants.** The trailing-window boundary in `drift_timeline` is not tested at all — the timeline is asserted for shape, not for which rows land in which window. The largest single gap left. |
| `backtest.py:200` | `return float(actual) != 0.0` | The MAPE zero-guard. Never tested with an actual of exactly zero. |
| `backtest.py:66,79` | `if len(index) == 0`, `if start > last_usable` | Degenerate-input guards in `make_cutoffs`, reachable only with series shorter than the tests use. |

`backtest.py:205` (`horizon_h % every == 0`, 6 mutants) is table-row selection for
the rendered markdown. Cosmetic; not worth a test.

## What this does *not* say

- It covers **two files**. The other ~4,500 lines are unmeasured. This is not a
  repo-wide quality figure and is not presented as one.
- 52.3% is a **low score**. Roughly half the small changes you could make to
  those two files would go unnoticed by the suite. The mitigating detail is
  *which* half: 120 of the survivor lines are prose, and the comparisons that
  drive the alarm are now pinned. The mitigating detail is not an excuse.
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
