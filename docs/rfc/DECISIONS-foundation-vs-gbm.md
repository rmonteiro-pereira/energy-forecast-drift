# Decisions — `foundation-vs-gbm`

The decisions the committee and the two adversarial rounds forced on
[`rfc-foundation-vs-gbm.md`](rfc-foundation-vs-gbm.md) (v4).
**Every reversal criterion is a test, not an opinion.**

Substrate: `energy-forecast-drift` @ `22473e019486c61ea7f066c04651a9d70aa4d03a`.
Date: 2026-08-06. Taken autonomously, under a mandate that said to decide everything.

---

## D01 — A lane in the existing repo, not a new one

**Reason.** The whole value of the finding depends on running against
`metrics/model.json`, which already carries `is_real=true`, `kind=eia_api_v2`,
`backtest.folds=55` and an honesty gate that bites. A new repo would have to
rebuild `models/backtest.py:111-125` and the 17,524-row panel — **which is
unreachable**, `.gitignore` holds `data/` — and would compare against a
*transcribed* `2.72%`, the failure mode `tests/test_doc_claims.py:3-9` documents.
Unanimous, 6/6 committee lenses.

**Reversal (test).** It becomes a new repo if, with the `foundation` extra absent,
`uv sync --extra dev --frozen && uv run ruff check . && uv run mypy && uv run pytest -v`
stops finishing green inside `timeout-minutes: 10` (`ci.yml:67`), **or** if
`uv run python -c "import torch"` starts exiting `0` in the `test` job.

---

## D02 — The code lives in `foundation/`, not in `models/`

**Reason.** It isolates the optional dependency outside the wheel and outside the
inherited `[tool.mypy] files`, and keeps `models/` free of an import CI does not
install.

**What this decision is NOT.** v2 justified `foundation/` by claiming it avoids
the `mutate` job (`timeout-minutes: 60`). **The claim was withdrawn in R1:**
`.github/mutation-paths.txt` also lists `pyproject.toml`, `uv.lock` and
`models/backtest.py`, and Phases 1 and 3 edit all three. The lane pays for the job
either way (F16).

**Reversal (test).** It moves back to `models/` if a test shows `foundation/`
falling outside the type-check or the wheel: `uv run mypy` reporting `Success` over
a `foundation/` file carrying a deliberate type error, **or** `foundation` missing
from `[tool.hatch.build.targets.wheel] packages` in a build.

---

## D03 — GIFT-Eval is cut entirely: data, harness and the name

**Reason.** It answers a different question (ranking TSFMs across 24 domains) and
would import a **data** licence gate that no condition of the implementer can
verify: offline agent, `.gitignore` holding `data/`, a 5,242,880-byte ceiling,
`timeout-minutes: 10`. Running it reproduces a public leaderboard rather than
measuring anything. **`energy-forecast-drift` already is the benchmark.**
Unanimous, 6/6.

**Reversal (test).** It reopens if some subset of GIFT-Eval runs end to end inside
the `test` job with no network, no GPU and no versioned file above 5,242,880 bytes
— demonstrated by a CI step that passes. Until that step exists, the cut holds.

---

## D04 — TimesFM is cut from v1; one TSFM only (Chronos-Bolt)

**Reason.** The finding is "zero-shot univariate against a GBM with covariates";
a second TSFM does not change it and doubles the download, the adapter and the
cost accounting. Weight measured: **1,995,406,976 B** (380.6x the ceiling).
Unanimous, 6/6.

**Reversal (test).** It reopens if the **95% CI** of
`r = mae(chronos_bolt@ctx671) / mae(lgbm_17_demand_only)`, by paired bootstrap over
the 55 origin blocks, **intersects** `[0.95, 1.10]`. **Not the point estimate** —
R1 showed the interval's width is of the same order as the band's, which makes a
point trigger a coin flip. The band is an "operational tie" that was **chosen, not
measured**, and that is stated. `arms[].id` is open and `timesfm_2p0_500m` is
pre-registered as a legal-but-absent value, so reopening is not a contract change.
Evaluating it is an acceptance of Phase 6.

---

## D05 — No model weights are versioned, at any size

**Reason.** Arithmetic, not preference: the smallest usable checkpoint
(`chronos-bolt-tiny`) is **34,622,352 B = 6.6x** the 5,242,880-byte ceiling.

**Reversal (test).** `git ls-tree -r -l HEAD | awk '$4 > 5242880'` must come back
empty. If it does not, the decision was violated — and that command is gate G6.

---

## D06 — The primary contrast is `chronos_bolt` against `lgbm_17_demand_only`

**Reason.** Three successive corrections, each one measured:

1. The committee proposed `lgbm_27` (27 features). The already-measured ablation
   says 7 of them are worth **−40.89%** of the MAE — scoring a univariate model
   against those measures the absence of covariates, not the model.
2. v2 proposed `lgbm_20_no_fcst` (`mae_without_forecast_weather = 5,159.56`,
   already in the artifact). **Still not univariate:** `temp_lag_168h`,
   `temp_last_1h` and `temp_roll_mean_24h` survive it — **observed** temperature
   in three shapes.
3. v3 proposed `lgbm_12_frozen` as the paired floor. **Measured, it is 71.04%
   worse than the seasonal naive** — see D07.

`lgbm_17_demand_only` is the honest ceiling of a GBM with no exogenous covariate,
refit every fold.

**Reversal (test).** The denominator changes if
`set(arms["lgbm_17_demand_only"].features) != set(build.FEATURE_COLUMNS) -
set(build.FORECAST_FEATURES) - {"temp_lag_168h","temp_last_1h","temp_roll_mean_24h"}`
— which is literally gate G13, and it refuses with
`failed_gate="arm-composition"`.

---

## D07 — `lgbm_12_frozen` is descriptive only, **out of the verdict's denominator**

**Reason.** Created in v3 to pair the refit cadence (1 fit against the GBM's 55,
against the TSFM's 0) and promoted to denominator of the pre-registered verdict.
Measured on the fixture: **MAE 4,363.64**, i.e. **+70.24% against the same arm
refit** and **+71.04% against the seasonal naive** — the trivial model this
repository exists to beat. With it in the denominator, a Chronos equal to the naive
would publish `r = 0.585` → *"wins"*, and the defeat band would require MAE
**2.14x the naive**: unreachable. **The amendment created to give a defeat
condition removed it.** And "same information" was false: the frozen arm trains on
11,144 rows against 16,328 (**−31.7%**) and its labels stop **54 days** earlier,
while the TSFM receives the whole expanding window.

**Reversal (test).** It returns to the denominator if a cadence-paired arm
satisfies `arms[].mae <= arms["seasonal_naive"].mae` — that is, if it at least
beats the naive. Until it does, it stays descriptive, labelled *"a floor of
cadence, not of information"*, with `fit_anchor_utc`, `train_rows_at_fit` and
`in_domain_training_hours` mandatory.

---

## D08 — The single fit is anchored at `cutoff_candidates[0]`, pre-registered

**Reason.** `refits == 1` does not say **at which** cutoff. G12 pinned `params`,
`num_boost_round` and `train_stride_hours` — none of the three is the anchor. A
free parameter sitting in the denominator, whose published bands are 25 percentage
points apart, and which moves the MAE by roughly 3x.

**Reversal (test).** The extended G12 refuses with `failed_gate="arm-cadence"` if
`arms[].fit_anchor_utc != cutoff_candidates[0]` or if `arms[].refits` diverges from
what was declared.

---

## D09 — Cost is CPU-seconds, on three lines that are never summed

**Reason.** Measured twice, because I got the first two wrong. Wall-clock is
disqualified **by demonstration**: (a) the CPU:wall ratio goes from **0.99** to
**26.1** by changing threads alone; (b) the wall time of the same work varied
**3.4x** (202.7 s against 59.9 s) with machine load; (c) giving LightGBM 32 threads
makes it **slower in wall time** (60.95 s against 55.67 s) and **29x more expensive
in CPU**. And `models/lgbm.py:53` freezes `num_threads: 0` into the published
params. Summing the lines hands the zero-shot TSFM a ~76x win that belongs to the
protocol (the refit is **98.7%** of the GBM's cost), not to the model.

**Reversal (test).** If an artifact carries any field summing two of the three
lines, or its `hardware` block fails its domain, G7 refuses with
`failed_gate="cost-provenance"`. Mandatory canary: an artifact with
`{"cpu_model":"","n_threads":0}` must fail.

**Methodological note on the record:** `params={"num_threads": 1}` **does not
serialise OpenMP** — only `OMP_NUM_THREADS=1` **in the environment** does (ratio
1.38 against 0.99, measured). Every measurement in the lane sets both.

---

## D10 — The verdict is evaluated over the full `cutoff_candidates`, not the intersection

**Reason.** G1 intersects fold sets to guarantee an identical `n`. But an
intersection is **survivorship filtering**: an arm that fails precisely on the
highest-error folds comes out with a lower MAE, and the gate reports green, giving
the artifact the appearance of a controlled comparison while the estimand changes
in silence.

**Reversal (test).** Each arm's unscorable folds are scored by the declared
pessimistic rule — **the `seasonal_naive` error on that fold** — and
`arms[].imputed_folds` is a mandatory field. If
`arms["chronos_bolt@ctx671"].imputed_folds > 0` and the Clause 5 verdict changes
band when the imputation rule is swapped for "drop the fold", the decision is wrong
and the verdict does not ship. That is the test, and it is executable in Phase 6.

---

## D11 — No gate exists until it has been seen failing

**Reason.** R2 confirmed **11 blockers, all with the same shape**: a gate specified
in prose that dies on the first command. G5 is green at HEAD; G6 prints the
violation and exits 0; G9 parses a summary that `-qq` never prints
(`pyproject.toml:45`); G2 is green on top of the edge gap that motivated it; G3
covers 1 fold of 55. **Four v3 amendments reintroduced the defect they were fixing.**

**Reversal (test).** There is no reversal — there is execution. Phase −1 requires,
per blocking gate, a dated transcript of the **observed red** pasted into the RFC,
plus a negative control. A gate with no red transcript is treated as nonexistent
and the phase depending on it does not start.

---

## D12 — F5 goes back to being a declared cut; G4 is scoped to the lane's artifact

**Reason.** v3 extended G4 across the whole `metrics/*.json` glob and withdrew the
carve-out, claiming that would close F5 "by construction". **False: G4 detects, it
does not fix.** Measured: `monitor.json` and `pipeline.json` have no `data` key, so
the gate would leave the suite **red on 2 of 6 artifacts the moment it lands**, with
no phase responsible for fixing them. Fixing `pipeline/daily.py` is another
mandate's scope, not a free ride on this lane.

**Reversal (test).** G4 covers the whole glob again once a test shows
`monitor.json` and `pipeline.json` already emitting `data: {kind, is_real}` — that
is, when the widened test passes without editing any artifact.

---

## D13 — The TSFM's minimum context window is 671 h, not 168 h

**Reason.** 168 h is the **backtest's** `min_history_hours` (warm-up), not the
features' reach. `features.build.MIN_HISTORY_HOURS = max(SEASON_OF_WEEK_LAGS) = 672`
is the lag depth measured from the **target**; measured from the **origin** the
reach is **671 h** at `h=1` (verified). Truncating the TSFM at 512 while the GBM
reaches 671 h is rigging the TSFM to lose.

**Reversal (test).** `arms["chronos_bolt@ctx671"].context_hours < 671` fails the
contract. Two pre-registered windows (`ctx671` and `ctx2048`) with distinct
`arms[].id`; publishing only one is a contract violation, not a choice.

---

## D14 — Chronos-Bolt's point reduction is `median_q50`, pre-registered

**Reason.** Chronos-Bolt is probabilistic and the seam requires a unique index
(`models/backtest.py:158`, `preds.loc[t]`). The primary metric is MAE and the
median is the L1-optimal functional. The opposite asymmetry has to be written down:
`models/lgbm.py:41-44` trains with `objective: "l1"` and the code's own comment says
that reporting L1 while optimising L2 is *"a small, common, avoidable mismatch"* —
**the GBM is optimised for the judged metric and the TSFM is not.**

**Reversal (test).** If `arms[].point_forecast` is absent or outside the enum
`{median_q50, mean, quantile_<q>}`, the artifact is not written. If swapping
`median_q50` for `mean` changes the Clause 5 verdict band, that ships as a
sensitivity rather than being hidden.

---

## D15 — Phase 2 has a code deliverable; "zero new dependency" was false

**Reason.** v3 claimed `models/train.py:118-150` (`ablate_forecast_weather`) was
enough. **Measured: it cannot reach 2 of the 3 arms.** Calendar is not a panel
column — `hour`, `dayofweek`, `month`, `is_weekend` and `is_holiday` are computed
inside `build_design_matrix` from the target. Dropping panel columns has a hard
floor of 17 informative features.

**Reversal (test).** `arms["lgbm_12_no_calendar"].features_informative == 12` with
the 27 columns preserved. If the mechanism produces fewer than 27 columns, G13 and
`features_informative` lose their premise and fail.

---

## D16 — G2 runs once, before the arms fork

**Reason.** v3 put the contiguity guard inside the TSFM adapter. The `lgbm_*` arms
do not pass through it — so on the same missing hour, Chronos would receive an
interpolated value and LightGBM would receive NaN consumed natively. **The gate
built to protect the comparison would violate Clause 1.** On top of that,
reindexing to `idx.max()` **cannot see a gap at the right edge** — the blackout
still open at forecast time, which is the common case in a day-ahead setting.

**Reversal (test).** The guard reindexes to `date_range(min, cutoff − 1h)`; a gap
touching `cutoff − 1h` fails with `failed_gate="contiguity"` and is **never**
imputed. Canary: a series with an edge gap must fail; a series with an interior gap
below the absolute ceiling must pass, recording `imputed_hours > 0`.

---

## D17 — The imputation budget is absolute, not relative

**Reason.** v3 used 1% of `len(history)` over an **expanding window**. On the real
panel that authorises **161.9 fabricated hours** (6.7 days) in silence; on the CI
fixture, a different number. A budget whose meaning changes with the length of the
series is not a budget. And imputing electricity demand by linear interpolation is
inventing data in a repository built entirely against that (`is_real`, the banner,
seven ADRs).

**Reversal (test).** A declared absolute ceiling, identical in both regimes; any
contiguous gap above it fails. If the same sentence authorises different counts of
fabricated hours on the fixture and on the real panel, the budget is wrong — and
that is checkable by comparing `arms[].imputed_hours` across the two.

---

## D18 — The anti-foresight probe runs per fold, with the arm rebuilt

**Reason.** v3 replaced the `mae == 0.0` canary — evadable by `if mae == 0.0` —
with an invariance probe that is **equally evadable**, by
`if cutoff == last_cutoff: be honest`. Measured: an arm reading the future on folds
1–54 and behaving on fold 55 comes out with `changed = 0 of 1320` and **MAE 58.11
against the naive's 2,551.25** — 43x better, gate green. Effective coverage:
**1 fold of 55**. And without rebuilding the arm from the perturbed series, not
even perfect foresight is caught (`changed = 0`, measured).

**Reversal (test).** 55 paired runs, one per cutoff, arm rebuilt. The canary this
decision must fail is exactly the adapter above: foresight on folds 1–54, honesty
on 55 → must fail with `failed_gate="foresight"`. Negative control: the
`seasonal_naive` does not trigger it.

---

## D19 — Stopping at v4

**Reason.** Every R2 blocker has the same shape — a gate verified by reasoning
rather than by execution — and therefore the same fix: **build the canary and watch
it fail.** Three rounds showed that an amendment written without execution produces
the next round of blockers; four v3 amendments reintroduced the defect they were
fixing. A v5 written the same way would produce a v6.

**Reversal (test).** A document round reopens if the implementation reveals a
**design** defect — not a code defect — that a reading round would have caught:
that is, one locatable in a section of the RFC without executing anything. A defect
that only appears when the gate runs does **not** count: that is exactly what
Phase −1 exists to find.

---

## D20 — `unscorable_cutoffs` becomes TWO fields

**Reason.** Found by running the G1 canary, not by reading the RFC. With arm B
failing on 10 folds, the intersection returned `{'A': 10, 'B': 0}` — and arm **A**
has `skipped_folds = 0`. That is: A lost 10 cutoffs to the intersection **because B
failed**, not through any failure of its own. One field cannot mean both things.

**Correction.** `arms[].unscorable_by_own_failure` (= `BacktestResult.skipped_folds`,
folds the arm itself could not score) and `arms[].folds_dropped_vs_intersection`
(folds the arm scored and lost because another arm failed). They are different
quantities, and the second is what exposes D10's survivorship filtering.

**Reversal (test).** On the G1 canary,
`arms["A"].unscorable_by_own_failure == 0` **and**
`arms["A"].folds_dropped_vs_intersection == 10`. If a single field produces both
numbers, it is wrong.

---

## D21 — The foresight probe's boundary is `>= cutoff_i`, written into the contract

**Reason.** Measured: with the perturbation applied at `> last cutoff` (36 of
4,801 h), the leaking arm comes out **`changed = 0`** — gate **green** — publishing
**MAE 58.11 against the naive's 2,551.25, 44x better**. With `>= last cutoff`
(37 h), it comes out `changed = 1` — caught, **by one prediction in 1,320**. The
entire gate's ability to detect depended on a character the RFC never wrote.

This is worse than finding R2-02 alleged ("coverage 1 fold of 55"): it is not low
coverage, it is **indeterminate detection**.

**Reversal (test).** The sneaky-arm canary (oracle on folds 1–54, honest on 55) must
be caught by the per-fold probe on **54 of 55** folds, and the `seasonal_naive` on
**0 of 55**. If swapping `>=` for `>` changes either number, the convention is not
pinned.

---

## D22 — G3 runs per fold in full on the TSFM and the stub; on the GBM arms, on a declared sample

**Reason.** Measured in Phase −1, and the RFC never accounted for it:

| subject | pairs | cost |
|---|---:|---:|
| deterministic stub (what the `test` job runs) | 13 | **0.3 s** |
| GBM, CI scale (`weeks=2`, 60 rounds, stride 12) | 13 | **62 s** |
| GBM, real scale (`weeks=8`, 300 rounds, stride 6) | 55 | **91.0 min per arm** |

Five GBM arms x 91 min ≈ **7.6 h**. It fits nowhere, and Phase 3 would have found
that out late.

**Decision.** G3 runs **per fold, in full (55 pairs)** on the stub and on the
`chronos_bolt@*` arms — the only ones with no internal leakage assertion. On the
`lgbm_*` arms it runs over a **declared sample of 8 of 55 folds, with the seed
recorded in the artifact**, because `WalkForwardLightGBM.__call__`
(`models/lgbm.py:127-131`) and `training_slice` (`:163-166`) already raise
`TemporalLeakageError` on their own — a second, independent guard the TSFM does not
have.

**Reversal (test).** The sample stops being enough if, on any run, an `lgbm_*` arm
is caught by the sample of 8 — that would mean LightGBM's internal guard is not
biting, and G3 goes to full coverage on all five arms, accepting the 7.6 h. The test
is literally `assert sampled_probe(lgbm_arm).caught == []`.

---

## D23 — `mutmut` only runs on this platform with `PYTHONIOENCODING=utf-8`

**Reason.** Measured: `uv run mutmut run` dies with
`UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f389'` — the
emoji from its own report, under the Windows console's cp1252. It never gets as far
as writing `.mutmut-cache`, and the three gate scripts then fail with *"No
.mutmut-cache found"*, a diagnostic pointing at the wrong place. The RFC anticipated
only that `untested` would count differently on Windows; the problem is upstream of
that — the tool does not run.

**Reversal (test).** `uv run mutmut run` without the variable must exit 0 and write
`.mutmut-cache`. Until it does, every mutation acceptance in the lane runs with
`PYTHONIOENCODING=utf-8 PYTHONUTF8=1`, and that goes in the phase, not in the head
of whoever is executing it.

---

## D24 — Every new test file covering a mutated path enters the runner AND the paths list

**Reason.** `tests/test_fold_identity.py` covered `models/backtest.py`, which is in
`[tool.mutmut] paths_to_mutate`, and was **not** in `[tool.mutmut] runner`. Measured
consequence: the 9 new tests never ran against the mutants of the code they exist to
protect, and two mutants of my own lines survived. With the file in the runner,
`models/backtest.py` went from **75.3% to 82.0%**.

The repo already has the guard against the two lists diverging
(`tests/test_mutation_config.py` recomputes the import closure and compares it with
`.github/mutation-paths.txt`), but it does not force a new test to be **included** —
only that the two lists agree with each other.

**Reversal (test).** For every file in `tests/` importing a module from
`[tool.mutmut] paths_to_mutate`, the name must appear in `[tool.mutmut] runner`.
That is computable from the AST, exactly as `tests/test_mutation_config.py` already
does for the import closure, and becomes a test in Phase 3b.

---

## D25 — Re-anchoring a survivor rule is expected maintenance, not a defect

**Reason.** Editing `models/backtest.py` shifted lines by +16 and +61, three rules in
`scripts/mutation_survivors.py` unhooked, and `--check` failed with 3 unadjudicated
survivors. This is **not a bug**: `scripts/mutation_survivors.py:57-59` matches on
`(file, line, snippet)`, and the comment at `:50-54` records that the snippet was
added after an episode in which a bare `(file, line)` pair kept matching across a
+25-line shift and three rules unhooked **in silence**. The design trades silence for
noise on purpose.

**Reversal (test).** After re-anchoring, `mutation_survivors.py --check` exits 0
**and** the snippets cited in the rules are still present on the new lines. If
`--check` ever passes with a rule whose snippet no longer exists on the line it
points at, the mechanism has rotted and the rule becomes content matching.

---

## D26 — Arm composition is verified structurally, never inferred from the data

**Reason.** The first version of `assert_composition` inferred composition by
counting non-null, non-constant features. That **cannot tell "blanked" from
"constant in this window"**. Measured: `is_holiday` has `nunique() == 1` over a
40-day fixture (no federal holiday falls in the window) and `== 2` over 200 days.
The sabotage canary — a twelve-feature arm built carrying thirteen — **passed** the
gate, silently, for a reason with nothing to do with the sabotage. A composition
gate inferred from data is falsifiable only by accident of the calendar.

**Correction.** Two halves, neither redundant: (a) the declared set matches the
spec; (b) every feature declared as dropped really is blank in the frame. The first
catches an arm built to the wrong spec; the second catches a spec declared and not
honoured — which is the case that matters, because the artifact is written from the
declaration.

**Reversal (test).** Two canaries, both in the suite: an arm built with `is_holiday`
back (wrong spec) and an arm declaring the right spec while applying another
(declaration not honoured). Plus a third test that **fails if the fixture window
contains no holiday** — without it the first two prove nothing, and that is the
lesson.

---

## D27 — A bare `uv run` rewrites the lockfile; CI needs `UV_FROZEN`

**Reason.** `uv.lock` turned up modified without `uv lock` ever being run. Only the
`uv sync --extra dev --frozen` step (`ci.yml:89`) uses `--frozen`; the eight `uv run`
steps after it (`ci.yml:93,94,100,103,108,114,121,141`) re-resolve against
`pyproject.toml` and rewrite the lock. Measured: **152 → 185 packages**, none
removed, no existing package version changed.

This is worse than the deadlock the RFC feared. The RFC assumed a relock would
require the network and therefore be a deliberate step; in practice it happens **in
silence**, on any machine with a network, from a command nobody reads as "modify a
versioned file".

**Reversal (test).** `UV_FROZEN: "1"` in the `test` job's `env` (a Phase 3b
deliverable), plus a test that runs some `uv run` and asserts `git diff --quiet
uv.lock` still holds. If the lock moves under a `uv run`, the gate fails.

---

## D28 — The `foundation` extra resolves torch from the CPU index

**Reason.** D27's accidental relock brought in **18 NVIDIA/CUDA packages** —
`nvidia-cudnn-cu13`, `cuda-toolkit`, `triton` and the rest — gigabytes of GPU wheels,
in a lane whose written premise is "no GPU guaranteed". Not a preference: a
contradiction between the lockfile and the execution conditions.

With `[[tool.uv.index]] pytorch-cpu` + `[tool.uv.sources] torch`: **18 → 0 CUDA
packages**, lock from 185 → 169, `torch 2.13.0+cpu`, and
`uv sync --extra dev --frozen` still **EXIT=0**.

**Reversal (test).** `test_the_lockfile_carries_no_cuda_wheels` — no line matching
`name = "nvidia*"` or `name = "cuda*"` in `uv.lock`. If they come back, either the
index unhooked or someone relocked without it.

---

## D29 — The guard repairs history and **never** touches an actual

**Reason.** The first version of `guard_contiguity` returned only the repaired grid,
which ends at `max(cutoffs) − 1h`. Measured consequence: every target hour
disappeared and `backtest.run` raised *"Every fold was unscorable"*.

The obvious correction — extend the grid over the actuals — is the wrong one, and
the distinction is the point: **interpolating history is a repair; interpolating an
actual fabricates the answer.** A missing actual has to stay missing so
`_is_scorable` drops that fold. That is the honest outcome, and the harness already
implements it.

**Reversal (test).** `test_the_guard_never_touches_an_actual`: the slice after
`max(cutoffs) − 1h` comes back identical to the original,
`actuals_untouched_from` is recorded in the report, and `backtest.run` over the
returned series still scores every fold. If the guard starts filling an actual, all
three fail.

---

## A recorded R2 false positive — R2-15

**Fact.** `R2-15` claimed the pair `mae_delta_pct: 518.68` + `horizons_won: 0/24`
"is not reproducible outside the exact scenario" and ordered it removed from §0 F1.
v4 complied. **Phase −1 reproduced the pair exactly**, in the scenario §0 always
described (NaN on 1 of 24 horizons, 10 folds).

**Consequence.** The pair returns to §0 F1 with the scenario named. And R2 — the
round that existed to catch R1's false positives — produced at least one of its own.
That does not invalidate R2; it confirms that **execution is the only reviewer that
does not get tired**, which is the law behind D11.

**Reversal (test).** If the pair stops reproducing under the named scenario, the cell
goes. Command: the Phase −1 G1 canary.

---

## A recorded honesty decision — R1 refuted nothing

**Fact.** R1: 73 findings, **73 CONFIRMED, 0 REFUTED**. The method's reference round
had 2 refuted out of 65. R2, given an explicit instruction to refute, returned
**4 refuted out of 60** — including one finding that, had it been accepted, would
have made the design worse (the contiguity guard).

**Consequence, accepted.** This v4 may carry amendments motivated by R1 false
positives. R2 identified six findings as `unjustified_amendment` and four were
reverted. **There is no guarantee it caught them all.** Recorded as risk 9 of the
RFC rather than hidden.

**Reversal (test).** Any v3 amendment whose original finding does not reproduce by
command in Phase −1 is reverted on the spot, and the reversal is recorded here.
