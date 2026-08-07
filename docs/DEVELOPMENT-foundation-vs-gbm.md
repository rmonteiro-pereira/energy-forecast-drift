# Developing the `foundation-vs-gbm` lane

**Scope: this lane only.** This file documents the branch `feat/foundation-vs-gbm-lane` — the
zero-shot foundation-model comparison that lives in `foundation/` plus the fold guarantees it forced
into `models/` and `features/`. It is **not** a development guide for `energy-forecast-drift` as a
whole; for that, `docs/REPRODUCE.md`, `CONTRIBUTING.md` and `docs/MUTATION-TESTING.md` are the
existing entry points and this file deliberately does not restate them.

**Why the filename is scoped.** There is no `docs/DEVELOPMENT.md` in this repository and this file is
not it. A file with that name would be read as the repo-wide developer guide, which is not what this
is and not what this branch is allowed to write; `docs/` here is already split by subject
(`REPRODUCE.md`, `MUTATION-TESTING.md`, `DRIFT-EVALUATION.md`, `adr/`, `rfc/`), and the lane's own
design documents already follow that pattern at `docs/rfc/rfc-foundation-vs-gbm.md` and
`docs/rfc/DECISIONS-foundation-vs-gbm.md`.

**Design is elsewhere; this is the operating manual.** The RFC records what was decided and what was
wrong. This file records what a person has to know to run the lane, change it, and not be fooled by
it. Where the two disagree, the disagreement is written down in [§8](#8-where-the-rfc-and-the-code-disagree)
rather than silently resolved — the RFC itself records three of its own §0 evidence claims being
falsified by a later round, so it is not treated here as ground truth about the code.

**Provenance of every number below.** Measured on **2026-08-06**, in a worktree at
`feat/foundation-vs-gbm-lane` @ `7bda784` (parent `22473e0` = `origin/main`), with four files modified
and `foundation/__main__.py` untracked at the time — the branch was being worked on while this was
written. Commands are given so each number can be re-taken rather than trusted.

---

## 1. What the lane is

A **Time Series Foundation Model** (TSFM) forecasting hourly electricity demand **zero-shot** — no
fitting on this panel at all — scored on the **same walk-forward folds** as the LightGBM that this
repository already publishes, and priced in CPU-seconds per prediction on the same machine.

The incumbent, from `metrics/model.json` (`is_real: true`, `data.kind: eia_api_v2`, PJM):

| | baseline `seasonal_naive_168h` | challenger `lightgbm_global_direct` |
|---|---:|---:|
| MAE (MWh) | 13,359.478 | **3,049.792** |
| MAPE | 11.727 % | **2.716 %** |
| n | 1,320 | 1,320 |

`metrics/model.json → metrics.comparison` records `mae_delta_pct: -77.17` and
`horizons_won: 24/24` — the GBM beats the seasonal naive on every one of the 24 horizons. That
`24/24` is the number the lane exists to put in context, and **it is not the number the lane tries to
beat**: see [§2](#2-the-comparison-contract).

The model under test is **Chronos-Bolt** (`amazon/chronos-bolt-small`), pinned by revision and
sha256 in `foundation/tsfm.py:55-78`. **TimesFM is cut from v1** (decision D04) with a reopening
criterion that is an interval, not a point estimate: `foundation/uncertainty.py:137
reopen_timesfm(ratio_ci, band=(0.95, 1.10))`. GIFT-Eval is cut entirely (D03).

Cost is the second half of the finding, not a footnote. It is measured on three lines that are
**never summed** (`foundation/cost.py:205 LINES`) — `fit_cpu_s`, `infer_cpu_s`, `load_cpu_s` — because
the refit is 98.7 % of the GBM's cost and a zero-shot model refits never. Summing them would hand the
TSFM a win that belongs to the harness rather than to the model.

### Layout

| path | what it is |
|---|---|
| `foundation/__main__.py` | the dispatch run — `python -m foundation`. **Untracked** as of the measurement above. |
| `foundation/compare.py` | assembles the artifact and runs every gate **before** anything is written |
| `foundation/guards.py` | G2 contiguity and G3 anti-foresight. Torch-free on purpose |
| `foundation/tsfm.py` | the Chronos-Bolt adapter. Importable without torch, unusable without it |
| `foundation/stub.py` | a deterministic zero-shot arm, positional by design. What CI actually runs |
| `foundation/cost.py` | `CostMeter`, `hardware_block`, `peak_rss_mb`, G7 |
| `foundation/uncertainty.py` | paired block bootstrap over origins, G10, `reopen_timesfm` |
| `models/arms.py` | the GBM ladder and the composition / params / cadence gates |
| `models/backtest.py` | `cutoffs=`, `rescore()`, `_summarise()` — the fold contract |
| `models/train.py` | `FoldIdentityError`, `align_arms()`, a `compare()` that refuses |
| `features/build.py` | `blank_features`, `informative_features`, `drop_features=` |
| `tests/fixtures/foundation.sample.json` | the permanent subject of the schema gates |
| `docs/rfc/` | the RFC and the 29 decisions, vendored into the repo |

---

## 2. The comparison contract

This is the project. Everything else is plumbing that exists to make one comparison honest.

**Zero-shot against a model trained on the data is not a comparison until the contract is explicit.**
A TSFM sees one univariate series. The published GBM sees 27 features, seven of which are weather
*forecasts* worth **40.89 %** of its MAE (`metrics/model.json → ablation.forecast_weather`, measured:
MAE 5,159.56 without against 3,049.79 with). Scoring those two against each other measures the
absence of covariates and publishes arithmetic that was already known.

**The inverse risk is equally real and easier to commit by accident: a TSFM configured to lose.** A
short context window, a mean reduction against an L1 metric, or a shorter fold set would each produce
a defeat that says nothing about the model. Both failure modes are closed by clauses, and each clause
is enforced somewhere executable.

| clause | the rule | where it is enforced |
|---|---|---|
| **1 — folds** | `cutoffs=` pins **candidates**, never the folds used. After every arm has run, intersect and re-score them all onto the intersection, recording per arm the two different ways it lost a fold | `models/backtest.py:247 rescore`, `models/train.py:92 align_arms` |
| **2 — horizon** | `range(1, 25)`, `cutoff_hour=12` UTC, `weeks=8` | `models/backtest.py:32-33,59` |
| **3 — context** | The TSFM's context floor is **671 h** — the GBM's deepest lag reach from the *origin*. Handing it less makes the result a statement about truncation | `foundation/tsfm.py:88,119-125` — raises, does not warn |
| **4 — covariates** | Declared per arm as a field. The zero-shot arm's `features` is `[]` and its `in_domain_training_hours` is `0` | `foundation/compare.py:206-219` |
| **5 — verdict** | `r = mae(TSFM) / mae(reference)`, the reference being the demand-only rung named in the ladder below. `r < 1.00` beats · `1.00–1.25` competitive · `> 1.25` not competitive — a publishable result. Evaluated over the **full** candidate list, not the intersection (Clause 1b) | pre-registered; `reference_arm` and `verdict` in the artifact |
| **6 — reduction** | `median_q50`. MAE is the judged metric and the median is its L1-optimal functional | `foundation/tsfm.py:162-166`, `quantile=0.5` |

### The ladder, and why the denominator is the demand-only rung

`models/arms.py:72-81`. Each rung removes exactly one kind of information, and the arm ids are
structural, not decorative:

```
lgbm_27              27 informative  everything, including forecast weather
lgbm_20_no_fcst      20              no forecast weather - still sees OBSERVED temperature
lgbm_17_demand_only  17              no weather at all - demand and calendar   <- DENOMINATOR
lgbm_12_no_calendar  12              demand only, refit every fold             <- information floor
lgbm_12_frozen       12              demand only, fitted once                  <- descriptive only
```

`lgbm_20_no_fcst` is the rung most likely to be mistaken for a fair anchor and is not one:
`temp_lag_168h`, `temp_last_1h` and `temp_roll_mean_24h` survive it
(`models/arms.py:45 OBSERVED_TEMPERATURE`), so it still reads a thermometer the univariate model
never sees.

The **frozen** rung is **out of the denominator** (D07) and this is the clearest example of a baseline
chosen to be beatable. The RFC's v3 put it in the denominator to "pair the cadence"; measured, it is
71 % worse than the seasonal naive, which would have made a Chronos merely equal to the naive publish
`r = 0.585` and "win". It stays as a descriptive arm with its handicap in a field
(`in_domain_training_hours`), and `assert_cadence` pins its single fit to `cutoff_candidates[0]`
because the anchor is a free parameter that moves its MAE by roughly 3x.

### The asymmetry that must stay written down

`models/lgbm.py` trains with `objective: "l1"`. **The GBM is optimised for the judged metric and the
TSFM is not.** Clause 6 is the most it can do about that; it does not erase it, and a reader of any
result has to be told.

### The interval, not the point

`foundation/uncertainty.py:63 paired_block_bootstrap` resamples **origins**, not predictions
(`BLOCK_KEY = "cutoff_utc"`), because the 24 horizons of one origin share a model state and a weather
regime. Measured on the RFC's 55-fold run, resampling the 1,320 rows independently reported an
interval **2.0x narrower**. `assert_block_is_origin` (G10) refuses an artifact whose block count does
not equal the fold count. The interval is mandatory in the artifact and **forbidden as a headline**.

---

## 3. The fold-reuse question, and where leakage gets in

### How the 55 refits over 8 weeks are defined

`models/backtest.py:80-109 make_cutoffs`, with `weeks=8`, `cutoff_hour=12`, `horizons=1..24`:

- `first_usable = index.min() + min_history_hours`, `last_usable = index.max() - max(horizons)`;
- `start = max(index.max() - 8 weeks normalised to 12:00 UTC, first_usable ceil to a day + 12 h)`;
- daily cutoffs from `start` to `last_usable`.

On the published panel (17,524 rows, ending `2026-08-02T00:00Z`) that is
`2026-06-07T12:00Z … 2026-07-31T12:00Z` inclusive — **55 daily origins**, matching
`metrics/model.json → backtest.folds = 55`, `skipped_folds: 0`, `n = 1320 = 55 × 24`. The GBM refits
once per origin, so 55 folds means 55 refits.

The midday cutoff is not arbitrary and `models/backtest.py:34-58` explains it: from a 00:00 origin,
horizon 24 is the only horizon whose target falls on the next calendar day, so it alone required a
weather run published at 12:00 — twelve hours *after* the origin. It was correctly withheld, and h24
was scored with all seven `fcst_*` features NaN, costing MAE 10,982 at h24 against 2,820 averaged over
h1-h23 on real demand. Moving the origin to midday fixes that without handing the model anything a
forecaster would not have had.

### Why reusing those folds for an external model is the easiest place to leak

Four distinct mechanisms, all of them silent:

**(a) Reusing a *scored* fold set instead of re-deriving candidates.** `metrics/model.json`'s 55 folds
are the folds **the GBM could score**. Handing that list to a second arm imports the first arm's
survivorship filter into the second arm's denominator. The lane never reads folds from an artifact:
`foundation/__main__.py:269` re-derives candidates from the raw index and hands the identical list to
every arm, including the TSFM.

**(b) `cutoffs=` pins candidates, not folds.** `models/backtest.py:179-186` drops a fold **whole** when
any one of its 24 horizons is unscorable, and scorability depends on what the *model* returned
(`_is_scorable`, `:282`). Two arms handed the same list can finish on different fold sets. This never
bit before because both existing models are deterministic and never emit NaN; a TSFM is this
repository's third `predict_fn` and the first with a real chance of failing a horizon. Hence
`rescore()` + `align_arms()`, and hence `compare()` raising `FoldIdentityError` instead of merging on
`horizon_h` and publishing a headline for two different experiments.

**(c) The intersection is itself survivorship filtering.** An arm that fails precisely on the hard
folds comes out with a *lower* MAE over the intersection. So both ways of losing a fold are reported
separately and never netted — `unscorable_by_own_failure` (an arm's own failure) and
`folds_dropped_vs_intersection` (folds it scored perfectly and lost because another arm failed). The
RFC's own Phase 1 run has a baseline with `own_failure = 0` that still loses ten folds; one counter
carrying both meanings would have reported it as failing on ten folds it scored perfectly.

**(d) Position versus timestamp.** `models/backtest.py:139` calls `series.dropna()` before slicing, so
a gap does not arrive as NaN — it arrives as a **shorter index**. Every model already in this repo
reindexes by timestamp and is immune. A TSFM consumes `history.to_numpy()[-context:]` — position. A
six-hour hole makes it wrong about the date of its own last observation by six hours, and since the
window is **expanding**, one gap contaminates every subsequent fold. That is why G2 runs **once, over
the experiment series, before the arms fork** (`foundation/__main__.py:279`) and not inside the
adapter: a guard in the adapter would give the TSFM an interpolated value and the GBM a native NaN,
which violates Clause 1 by way of the gate meant to protect it.

**The boundary the guard will not cross:** it repairs *history* and never an *actual* (D29). The
repair grid stops at `max(cutoffs) - 1h`; past that instant the series is the answer, and imputing an
answer fabricates the measurement. A missing actual stays missing, `_is_scorable` drops the fold, and
that is the honest outcome. `foundation/__main__.py:148 _guarded_panel` extends the same rule
sideways: an hour the guard fabricated arrives at the GBM with **NaN weather**, not a neighbour's
temperature.

### And the seam has no leakage protection of its own

`models/backtest.py:112 run` will happily score a prescient `predict_fn`: `lambda h, t, c:
series.reindex(t)` returns MAE 0.0 and raises nothing. `ChronosArm.__call__` asserts
`history.index.max() < cutoff` (`foundation/tsfm.py:140-143`), but an assertion inside one adapter is
not a property of the harness. G3 is what makes it checkable, per fold, with the arm rebuilt from the
perturbed series.

---

## 4. Phase −1 and the eleven gates

The RFC's entry rule (D11): **a gate that has not been seen failing does not exist.** Write the canary
first, run it, observe red, paste the output, *then* implement the gate, then prove it stays silent on
the honest case.

Read the status column literally. Three different things can be true of a gate and they are not
interchangeable:

- **transcript** — seen red on 2026-08-06 against pristine `22473e0`, with the output pasted into
  `docs/rfc/rfc-foundation-vs-gbm.md §4.−1`. The canaries were **not** left in the repository, so
  those reds are a dated record and are not re-runnable today.
- **red-state test in repo** — a test that fails if the gate is removed or weakened, living in the
  suite, with a negative control. This is the only status that keeps proving itself.
- **re-measured today** — I ran it while writing this file; the command is in [§6](#6-running-it).

| gate | blocks | what it refuses | transcript | red-state test in repo | re-measured today |
|---|:--:|---|:--:|---|:--:|
| **G1** fold-identity | yes | Publishing a comparison over divergent fold sets; a `compare()` with no `n` | yes | `tests/test_fold_identity.py` — `test_compare_refuses_arms_scored_on_different_folds`, `test_align_arms_separates_the_two_ways_an_arm_loses_a_fold`, `test_align_arms_raises_when_the_arms_share_no_fold` | yes (full suite) |
| **G2** contiguity | yes | A gap at `cutoff-1h`; a run longer than `MAX_IMPUTED_RUN=3`; more than `MAX_IMPUTED_HOURS=24` total | yes | `tests/test_foundation_lane.py` — `..._refuses_a_hole_at_the_right_edge`, `..._refuses_a_long_interior_run`, `..._refuses_too_many_hours_in_total`, `test_the_guard_never_touches_an_actual`, `test_the_guard_hands_every_arm_the_same_series` + negative control | yes |
| **G3** anti-foresight | yes | An arm whose forecast moves when only the post-cutoff future moves | yes | `tests/test_foundation_lane.py` — `..._catches_perfect_foresight`, `..._catches_an_arm_that_only_cheats_on_some_folds`, `test_the_probe_must_rebuild_the_arm_or_it_sees_nothing`, `test_the_perturbation_boundary_is_inclusive` + negative control | yes |
| **G4** provenance schema | yes | A lane artifact whose `data` block does not mirror `is_real`; a synthetic artifact at the published path | yes | `tests/test_lane_artifact.py` — `test_the_artifact_answers_is_real_in_both_places`, `test_metrics_foundation_json_is_real_or_absent`, `test_the_fixture_exists_and_is_not_empty` (anti-vacuum) | yes |
| **G5** no torch in CI | yes | An adapter that drags torch into `sys.modules` on import; torch outside the `foundation` extra; a CI sync line asking for that extra | yes | `tests/test_foundation_lane.py:53,62,79` + the CI step at `.github/workflows/ci.yml:127-140` | **yes, under the strongest available conditions** — see below |
| **G6** nothing versioned > 5,242,880 B | yes | A committed object over the ceiling — reading the **object**, and exiting non-zero | yes | CI step only (`ci.yml:148-151`). The canary that made it red is not in the repo | command re-run: exit 0 |
| **G7** cost provenance | yes | A placeholder hardware block; a missing cost line; any field that collapses two lines into one, **by name or by value** | yes | `tests/test_cost.py` — nine `test_g7_*` cases including `..._refuses_a_total_hiding_under_a_harmless_name` and the negative control `..._does_not_cry_wolf_when_a_line_is_zero` | yes |
| **G8** live prose pinned | yes | README prose naming a lane arm while no published artifact exists to have read the number from | yes | `tests/test_doc_claims.py:106` — **conditional and currently vacuous by design**; see the warning below | yes (passes; nothing to bite) |
| **G9** zero skips in the lane | yes | A skipped test in the lane suite reporting green; a glob that matches nothing | yes | CI step (`ci.yml:167-184`) + `tests/test_workflows.py` recomputing the derived file list | yes — **90 passed, 0 skipped** |
| **G12** arm-params / cadence | yes | An artifact declaring hyperparameters the booster was not fitted with; a frozen arm with the wrong refit count or anchor | yes | `tests/test_arms.py` — `test_params_gate_reads_the_booster_not_the_declaration`, `test_cadence_gate_pins_the_frozen_anchor`, `test_a_frozen_arm_fits_once_and_a_refit_arm_fits_every_fold` | yes |
| **G13** arm-composition | yes | An arm carrying a feature its rung forbids, on **all** rungs, checked structurally | yes | `tests/test_arms.py` — `..._catches_an_arm_built_to_the_wrong_spec`, `..._catches_a_declaration_the_frame_does_not_honour`, `test_is_holiday_only_varies_on_a_long_enough_window` + negative control | yes |
| **G10** uncertainty | no | An interval resampled over predictions instead of origins; a block count that is not the fold count | — | `tests/test_uncertainty.py` — `test_g10_refuses_an_interval_resampled_over_points`, `..._refuses_a_block_count_that_does_not_match_the_folds` + negative control | yes |
| **G11** dashboard | no | — | — | **nothing** | **undecided — see below** |

### The three statuses that are weaker than they look

**G6's red state is not currently reachable from the repository.** The gate is a `run:` step and its
canary — a synthesised `git ls-tree` line over the ceiling — was not committed. What is verifiable
today is only that it is green and that it reads the right fields. Re-measured: `git ls-tree -r -l
HEAD | awk '$4 > 5242880 …'` → exit 0; largest committed object `uv.lock`, 917,293 B. Two independent
defects were reproduced against the *old* wording (a false positive from reading the worktree instead
of the object, and a false negative that printed the violation while exiting 0), so the current
wording matters; nothing in the suite would notice if it regressed.

**G8 is armed but has no subject.** It fires only if `README.md` names a lane arm, and today it does
not, so the assertion is true over the empty set. That is deliberate — a pin written as "every lane
number matches the artifact" would have been vacuously green and stayed green until the first sentence
about the lane was written, which is exactly when nobody is looking. It should be read as *an
outstanding obligation recorded in a runnable place*, not as a gate currently doing work.

**G11 was never decided either way.** The RFC's own wording is "include it, or declare in writing that
it stays out". Measured: `dashboard/src/useMetrics.ts:65-72` fetches five fixed artifacts and
`foundation.json` is not among them, and `docs/rfc/DECISIONS-foundation-vs-gbm.md` contains no
decision mentioning the dashboard. So the lane is out of the dashboard **by omission**, which is the
one outcome the gate asked not to happen. Closing it means writing the decision, not writing code.

### G5, re-measured under the strongest available conditions

`torch` and `chronos` **are** installed in the worktree's `.venv` (the `foundation` extra was synced
locally so the adapter could actually run). Under exactly that condition:

```
torch installed in .venv: True
chronos installed      : True
torch in sys.modules after importing foundation.tsfm: False
```

That is the only one of G5's three conditions with a reachable red state, and it was proved with the
loaded gun in the room rather than with torch absent — where conditions (1) and (2) are satisfied by
an empty repository and prove nothing.

---

## 5. Current state — implemented versus designed

**Implemented, committed, and covered by tests in the suite** (all re-run 2026-08-06):

- the fold contract — `cutoffs=`, `rescore()`, `_summarise()`, `FoldIdentityError`, `align_arms()`,
  a `compare()` that refuses and emits `n`;
- the arm ladder and its three gates — `models/arms.py`, `features.build.blank_features` /
  `informative_features` / `drop_features=`;
- both lane guards — `guard_contiguity` (G2) and `foresight_probe` / `assert_no_foresight` (G3),
  torch-free;
- the Chronos-Bolt adapter with a lazy import and a 671 h context floor, plus a deterministic stub;
- cost metering and G7, with `ram_gb` and peak RSS read from the standard library on both platforms;
- the paired block bootstrap over origins, G10, and `reopen_timesfm` on the interval;
- the artifact assembler, the fixture subject, and the three CI steps for G5/G6/G9;
- `pyproject.toml`: the `foundation` extra, `foundation` in `[tool.mypy] files` and in the wheel, and
  torch pinned to the CPU index.

**Uncommitted at the time of measurement** (the branch was actively being worked on — re-check before
relying on any of it):

- `foundation/__main__.py` — **untracked**. This is the dispatch command; without it the lane had
  every gate and no way to run;
- `models/lgbm.py` — a `fit_cpu_s` accumulator inside `WalkForwardLightGBM`, because the refit happens
  *inside* the call the harness meters as inference, so no caller could ever start a fit timer;
- `foundation/compare.py` — a `foresight` field, so G3 leaves a trace in the record;
- `foundation/tsfm.py` — the `predict_quantiles` batch passed **positionally** (the first argument is
  `context` in chronos-forecasting 1.x and `inputs` in 2.x; the lock resolves 2.3.1);
- `tests/test_lane_artifact.py` — `test_an_arm_that_refits_reports_what_the_refit_cost`, the converse
  that was missing while the fixture sat in the hole with 13 refits at `fit_cpu_s: 0.0`.

**Designed, not done:**

- **`metrics/foundation.json` does not exist.** The published artifact is defined as *real or absent*
  and is enforced in two places — `foundation/__main__.py:341 refuse_to_publish_a_fixture` at the
  writer and `tests/test_lane_artifact.py:145` at the gate. There is therefore **no result yet**, on
  real data, for anything in this lane;
- `ctx=2048` — Clause 3 pre-registers two arms, `ctx=671` (parity) and `ctx=2048` (native maximum).
  Only the floor is wired: `--context-hours` exists, nothing names 2048, and only one context appears
  in the fixture;
- ~~**Clause 1b's pessimistic imputation**~~ — was the largest hole this document found and is now
  closed (`foundation/imputation.py`); see §8 row 1;
- TimesFM — cut from v1 by decision, with `reopen_timesfm` in place as the reopening criterion;
- G11 — undecided, as above.

**What the fixture artifact currently says.** `tests/fixtures/foundation.sample.json` —
`is_real: false`, `data.kind: synthetic_fixture`, four arms, 13 folds, n = 312, produced by the
committed command in §6 with a real Chronos-Bolt checkpoint.

> **The numbers are deliberately not reproduced here.** They were, in the first draft of this file,
> as a table of MAEs beside the arm ids — and that is precisely what
> `tests/test_doc_claims.py` exists to catch. The gate scans every tracked markdown file, this one
> included, and the table put it red. The table came out rather than the gate being widened: a
> development guide that has to be exempted from the project's honesty gate is a guide teaching the
> wrong habit.
>
> Read the artifact instead — `python -m json.tool tests/fixtures/foundation.sample.json` — where
> every number sits next to the `is_real: false` that qualifies it. Two things in it are worth
> knowing before you look: the ordering of the two GBM rungs is **inverted** relative to the 55-fold
> real-panel run, which is what a 13-fold synthetic window is worth; and the zero-shot arm's peak RSS
> is roughly **3.4x** the GBM's, which is the one comparison a synthetic panel does not distort.

---

## 6. Running it

### Offline, no GPU, no key

```bash
uv sync --extra dev --frozen                       # what CI installs: no torch
OMP_NUM_THREADS=1 uv run --frozen python -m foundation \
    --source synthetic --weeks 2 --tsfm stub --out /tmp/lane.json
```

Measured 2026-08-07 on this machine: **exit 0, 23 s wall**, 13 folds, and

```
arm                                 MAE  imputed     MAE_isec    fit_s  r vs ref
seasonal_naive                 2,757.39        0     2,757.39     0.00     1.244
lgbm_17_demand_only            2,216.64        0     2,216.64     7.20     1.000
lgbm_12_no_calendar            2,358.47        0     2,358.47     5.98     1.064
stub_zero_shot                 2,757.39        0     2,757.39     0.00     1.244

reference: lgbm_17_demand_only   verdict base: 13 fold(s)   intersection: 13
  rule: seasonal_naive_error_on_unscorable_fold
  lgbm_12_no_calendar/...: r=1.064 (competitive) | dropping instead of imputing: r=1.064 (competitive)
  stub_zero_shot/...:      r=1.244 (competitive) | dropping instead of imputing: r=1.244 (competitive)
  lgbm_12_no_calendar/...: 95% CI [1.008, 1.131] over origins
  stub_zero_shot/...:      95% CI [1.134, 1.352] over origins
```

Three things in that output are worth reading rather than skimming. `seasonal_naive` appears without
being asked for, because Clause 1b charges an unscorable fold the naive's error on that fold and the
run refuses without it. `imputed` is **0** on every row and `MAE_isec` equals `MAE` — on a fixture
where every arm scores every fold the two rules coincide exactly, which is why Clause 1b could go
unimplemented through three adversarial rounds. And the stub's MAE is identical to the naive's to the
cent, which is the stub working as designed: it is a seasonal naive computed by *offset* instead of
by timestamp, so on a gapless grid the two must agree.

`OMP_NUM_THREADS` is not optional. Without it the run refuses before doing any work
(`foundation/__main__.py:123`), measured: **exit 2**, with the reason. See the warnings.

Useful flags: `--arms all` for the whole ladder; `--tsfm none` to run the GBM rungs alone;
`--probe-gbm-folds N` for G3's coverage on the refit arms (default 3 — full coverage is roughly
91 min per GBM arm at real scale, which is decision D22, not an oversight); `--probe-tsfm-folds 0`
meaning *every* fold for the zero-shot arm, which has no leakage assertion of its own.

### With the real checkpoint (needs network, still no GPU)

```bash
uv sync --extra dev --extra foundation --frozen     # ~190 MB checkpoint, fetched at load()
OMP_NUM_THREADS=1 uv run --frozen python -m foundation \
    --source synthetic --weeks 2 --tsfm chronos --out /tmp/lane-chronos.json
```

Nothing downloads at import time; `ChronosArm.load()` (`foundation/tsfm.py:127`) is the only fetch and
it belongs to a dispatch run, never to CI. **No usable checkpoint fits under the 5 MiB ceiling** —
34,622,352 B at the smallest, 6.6x — so weights are never vendored and never versioned (D05).

Running against **real** data additionally needs an EIA key (see `docs/BLOCKED.md`) and
`--source real`. Only such a run may write `metrics/foundation.json`; anything else is refused at the
writer.

### The lane's own test slice

```bash
uv run --frozen python -m pytest -o addopts= -p no:cacheprovider --no-header -rN \
    tests/test_arms.py tests/test_cost.py tests/test_foundation_lane.py \
    tests/test_lane_artifact.py tests/test_uncertainty.py
```

Measured: **90 passed, 0 skipped, 3.92 s**. Whole suite: **495 collected**.

### What CI covers

`.github/workflows/ci.yml`, job `test`, with `env: UV_FROZEN: "1"` at `:76-77` and
`uv sync --extra dev --frozen` at `:99`:

- ruff, ruff-format, mypy over 42+ source files including `foundation`;
- the full pytest suite (`:113`);
- **G5** (`:127-140`) — torch must not be importable in the test job, and importing
  `foundation.tsfm` must leave `sys.modules` clean;
- **G6** (`:148-151`) — no committed object over 5,242,880 B;
- **G9** (`:167-184`) — the lane test files, derived by grep from their imports, must run with zero
  skips and must not collect nothing;
- the pre-existing smoke tests, artifact-provenance checks and the `metrics/` size guard.

### What CI does **not** cover — read this before trusting a green tick

- **CI never runs `python -m foundation`.** There is no dispatch step. The comparison itself is
  exercised only through unit tests and the committed fixture;
- **CI never installs torch and never downloads a checkpoint.** The zero-shot arm under CI is
  `foundation.stub`. CI proves the *contract*; it proves nothing about any model;
- **no GPU, and none is assumed anywhere** — `torch` resolves from the CPU index by construction;
- **no real data.** Every smoke step runs `--source synthetic`. `metrics/foundation.json` is never
  produced in CI;
- **G3's real cost is never paid.** CI probes a handful of folds on a deterministic stub;
- **`tests/test_fold_identity.py` is outside G9's no-skip gate.** The CI step derives its file list
  from imports matching `^(from foundation|import foundation|from models import .*\barms\b|from
  models\.arms)`; that file imports `from models import backtest, baseline, fixtures, train` and does
  not match. Measured: the derived list is five files, and G1's red-state tests are not among them.
  They still run in the main `pytest` step — but a `skip` added there would not be caught by the gate
  built to catch exactly that;
- **the 60-minute `mutate` job fires for this lane.** `.github/mutation-paths.txt` lists `models/**`,
  `features/**`, `pyproject.toml` and `uv.lock`, all of which this branch touches. `foundation/**` is
  not in the list, but that does not buy an exemption.

---

## 7. Known traps

Each of these was paid for once. They are written as warnings because the pattern that produced them
is still available to anyone editing this lane.

> **⚠ 1 — The cost table was mislabelled CPU-versus-wall twice.** v2 published wall-clock under a CPU
> heading. v3 redid the measurement and **repeated the same mistake**, because
> `params={"num_threads": 1}` does *not* serialise OpenMP: it gave CPU 71.7 s against wall 52.1 s, a
> ratio of 1.38 that is impossible for one thread. Only `OMP_NUM_THREADS=1` **in the environment**
> brings it to 0.99. Wall-clock is disqualified as a unit outright — the identical workload measured
> 202.7 s on a loaded machine and 59.9 s on an idle one, and a number that disagrees with itself by
> 3.4x cannot decide whether a foundation model is cheaper. `foundation/__main__.py:123` now refuses
> to start when the environment and `--n-threads` disagree; do not remove that check to make a
> command shorter.

> **⚠ 2 — Never sum the cost lines.** `fit_cpu_s + infer_cpu_s` hands the zero-shot arm a win that
> belongs to the harness: the refit is 98.7 % of the GBM's cost and 55 refits is a choice this
> repository made. G7 refuses totals **by name** (`total_cpu_s`, `cpu_s`, `cost_per_prediction`,
> `seconds`) **and by value**, because the interesting version of the mistake is a field called
> something innocent like `elapsed` holding `fit + infer`.

> **⚠ 3 — Four of v3's amendments reintroduced the defect they were correcting.** G5's rewording was
> green at HEAD with zero lines of lane code in the repository. G3's probe perturbed only the tail and
> covered **1 fold of 55** — an arm reading the future on folds 1-54 came out clean with MAE 58
> against the naive's 2,551. G2's guard reindexed to `idx.max()`, which cannot see a hole at the right
> edge — the commonest gap in a day-ahead setting. The frozen rung was added to give the verdict a
> defeat condition and, in the denominator, removed it. **Treat any amendment written without
> execution as presumed defective.** That is what Phase −1 is for and why D11 exists.

> **⚠ 4 — A canary that passes for the wrong reason is an unverified gate.** Two of the three CI
> canaries did exactly that on their first run: G6's compared the wrong awk fields, so `"blob" >
> 5242880` was a *string* comparison that happened to be true; G5's did `import json as torch`, which
> puts `json` in `sys.modules` and not torch. The Phase −1 rule applies to the canary as much as to
> the gate — check *why* it went red, not just that it did.

> **⚠ 5 — `pyproject.toml` sets `addopts = "-q"`.** Any invocation adding another `-q` becomes `-qq`
> and pytest prints **no summary line at all**. A gate parsing "N passed / N skipped" out of such a
> run is green precisely when there are skips. Always `-o addopts=` when a command's *output* is being
> parsed.

> **⚠ 6 — A bare `uv run` re-resolves and rewrites `uv.lock`.** Only the `uv sync` step uses
> `--frozen`. Measured: adding the `foundation` extra and running a bare `uv run` took the lock from
> 152 to 185 packages with no `uv lock` ever typed — including eighteen NVIDIA/CUDA wheels, gigabytes
> for hardware this lane declares it does not have. `env: UV_FROZEN: "1"` covers the CI job; locally
> pass `--frozen` or export it. If a CUDA wheel returns to the lock, a test fails
> (`test_the_lockfile_carries_no_cuda_wheels`).

> **⚠ 7 — With the `foundation` extra installed locally you cannot reproduce the CI G5 step.** Its
> first condition asserts torch is *not* importable, and in a worktree synced with `--extra
> foundation` it is — measured today. Reproduce condition (3) instead (`import foundation.tsfm`, then
> assert `"torch" not in sys.modules`); it is the only one with a reachable red state anyway.

> **⚠ 8 — `mutmut` will not run on Windows without `PYTHONIOENCODING=utf-8`** (D23). It dies with
> `UnicodeEncodeError` on its own emoji under cp1252, upstream of anything this repository controls.
> And any new test file covering a mutated path must be added to **both** `[tool.mutmut] runner` and
> `.github/mutation-paths.txt` (D24) — adding `tests/test_fold_identity.py` to the runner moved
> `models/backtest.py` from 75.3 % to 82.0 %, which means it was not being measured before.

> **⚠ 9 — Naming an arm id in published prose turns the suite red, including here.**
> `tests/test_doc_claims.py` scans **every tracked markdown file** — not just `README.md` — for the
> arm ids listed in its `LANE_ARMS`, and requires `metrics/foundation.json` to exist, be
> `is_real: true` and carry no `failed_gate`. It does not exist. Only `docs/rfc/` is exempt, because
> it is the document that chose the arms before any result existed, and fenced blocks are stripped as
> dated transcripts.
>
> That is why this file writes *"the demand-only rung"* rather than the id, and why its fixture table
> was deleted rather than exempted. This guide was briefly on the exemption list and came off it: a
> development guide that needs an exemption from the project's honesty gate is teaching the habit the
> gate exists to prevent. The ids live in the fenced ladder in §3, which is where the gate agrees they
> belong. The README sentence is the *last* step, after the dispatch run publishes.

> **⚠ 10 — F5 is an open defect, declared, not fixed.** Measured today: `metrics/monitor.json` and
> `metrics/pipeline.json` have **no `data` block at all** while carrying `is_real: true` at the top
> level, so the pytest half of the honesty gate *skips* them and the CI half reads `kind` only from
> `data.kind`. G4 is deliberately scoped to the lane's own artifact (D12), because extending it across
> the whole glob would leave the suite red on 2 of 6 artifacts with no phase responsible for fixing
> them. Fixing F5 is its own mandate; do not let this lane absorb it.

> **⚠ 11 — `metrics/model.json` is regenerated by `train.yml` and can move under the lane.** Every
> incumbent number quoted in this document — 55 folds, MAE 3,049.79, 24/24, the 40.89 % ablation —
> comes from an artifact a scheduled workflow rewrites. Re-read it rather than quoting this file.

> **⚠ 12 — On this Windows shell, `grep` is shimmed to ripgrep.** The CI G9 step's `grep -rlE …` line
> fails locally with `unknown encoding: -e`. That is a property of this machine, not of the workflow;
> derive the file list with `git grep -lE` or the ripgrep spelling when checking it by hand.

---

## 8. Where the RFC and the code disagree

Checked against the tree, not against the document.

| # | the RFC says | the code does | assessment |
|---|---|---|---|
| 1 | **Clause 1b / D10** — the verdict is evaluated over the **full** `cutoff_candidates`, with each arm's unscorable folds imputed at the `seasonal_naive` error, and the artifact carries `arms[].imputed_folds` plus the rule used. The intersection is published only as a secondary number | **Closed** by `foundation/imputation.py`. `arms[].mae` is the Clause 1b number, the intersection survives as `mae_intersection`, the naive is scored unconditionally as the imputation source, and an artifact without it is refused with `failed_gate: "imputation"` | **Was** the lane's headline decision, unimplemented — this row is what found it. Manufacturing the failure the fixture never produces (an arm exact where it answers, silent on the hard stretch) puts `r` at **0.000 / "beats"** over the intersection and **1.212 / "competitive"** under Clause 1b, on identical data. D10's reversal criterion is now a field, `verdict[].bands_agree` |
| 2 | §2.3 requires `arms[].train_rows_at_fit` | the artifact carries `in_domain_training_hours` and no `train_rows_at_fit` | Field renamed, arguably improved — hours are comparable across arms where row counts depend on the training-origin stride. But it is a silent divergence from a normative list |
| 3 | Clause 3 pre-registers **two** context arms, `ctx=671` and `ctx=2048` | only the 671 h floor exists (`MIN_CONTEXT_HOURS`); `--context-hours` is a free parameter and nothing pins 2048 | Pre-registration not honoured yet. A context chosen after seeing results is the classic way a comparison stops being one |
| 4 | §3 G11: "include it, or declare in writing that it stays out" | the dashboard fetches five fixed artifacts, `foundation.json` is not one, and no decision records the omission | Undecided by omission — the outcome the gate asked to prevent |
| 5 | §0 F1 quotes the fixed string `"identical folds and horizons for both models"` in `build_artifact` | `models/train.py:348-356` replaced it with a claim naming its own enforcement — but `metrics/model.json` (generated 2026-08-02, before the lane) still carries the old string | Code fixed, published artifact stale. It will correct itself on the next `train.yml` run; until then the artifact and the code disagree |
| 6 | §4.−1 says Phase −1 is closed with 11 transcripts, and later sections report Phases 0-7 green | the branch carries all of that plus Phase 6, committed: `foundation/__main__.py`, the `fit_cpu_s` accumulator, the positional `predict_quantiles` fix, and `foundation/imputation.py` | The lane is **well past Phase −1**. Any instruction to "enter at Phase −1" is stale; what remains is the dispatch run itself, which needs `EIA_API_KEY` |
| 7 | §0 F17 — `pytest -q` prints no summary; §0 F18 — only `uv sync` uses `--frozen` | both fixed for the lane's own steps (`-o addopts=` in G9, `UV_FROZEN` on the job) | Consistent. Recorded because the underlying `addopts = "-q"` is still in `pyproject.toml` and will trap the next command that parses pytest output |

**Not verifiable from here, and not asserted:** the RFC's 55-fold measurements (the MAE ladder, the
91-minutes-per-arm G3 budget, the 2.0x interval width, the 98.7 % refit share) were taken on a
200-day fixture run that is not committed. Nothing in this document re-derives them; where they are
quoted, they are quoted as the RFC's record and labelled as such. The only 55-fold numbers verified
here are the ones inside `metrics/model.json`.
