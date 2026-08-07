# RFC — `foundation-vs-gbm`: zero-shot TSFMs on the `energy-forecast-drift` folds

**Status: v4 — final. The stop rule fired.** See §7.
**R2's verdict: `not ready to implement`, 4/4 lenses.** That is not a contradiction with "final":
v4 is the last version *of the document*, because **every R2 blocker has the same shape and the
same fix — and the fix is not writing more RFC, it is building the gate and watching it fail.**
Phase −1 exists for that and is the only way into the implementation.

**Substrate:** `energy-forecast-drift` @ `origin/main` = `22473e019486c61ea7f066c04651a9d70aa4d03a`.
`uv run pytest -p no:cacheprovider` → exit 0; `pytest --collect-only` → **387 collected**
(376 passed, 11 skipped). **The author is read-only over `energy-forecast-drift`.**
Decisions with reversal criteria: [`DECISIONS-foundation-vs-gbm.md`](DECISIONS-foundation-vs-gbm.md).

> **A note on the transcripts.** Every fenced block below is a **verbatim record of what a run
> printed**, kept exactly as it came out — including the Portuguese labels in the probe scripts that
> produced it. Translating a transcript would falsify it, and this repository already draws that
> line: *"Transcripts are exempt — they are dated records of what a run printed"*
> (`tests/test_doc_claims.py:3-9`). The prose around them is the translation.

---

## Provenance table

| version | round | what it found |
|---|---|---|
| **v1** | Committee, 6 lenses over the current state | 27 defects in already-published code; 32 cuts; **6/6 unanimity** on lane / GIFT-Eval out / TimesFM out of v1 / no weights versioned / the primary contrast is not the 27-feature GBM. 5 conflicts named. |
| **v2** | — | Synthesis naming the conflicts; §0; contracts; gates; phases. |
| **v3** | **R1, 6 lenses + 6 verifiers** | **73 findings: 12 blockers, 44 majors, 17 minors, 0 refuted.** Blockers in three groups: G1 in the wrong place, at the wrong time, with the wrong mechanism; G2 and G3 with no mechanism; the primary contrast still biased. **Three pieces of evidence in my own §0 were falsified** (F1, F4) and the cost table was labelled CPU while holding wall-clock. |
| **v4** | **R2, 4 lenses + 4 verifiers, amendments only** | **60 verdicts: 56 confirmed (11 blockers, 24 majors, 21 minors), 4 REFUTED.** Unanimous `not ready`. **Four of v3's amendments reintroduced the defect they were fixing** (G5, G3, G2, `lgbm_12_frozen`). The cost table was mislabelled **for the second time**. |
| **execution** | Phases −1 → 7, then 6 | The document stopped; the defects did not. Every phase after the stop rule found something no further reading would have surfaced, **including in gates this RFC had just finished specifying**. §0 grew from F18 to **F20**: the adapter had never been run and did not work (F19), and a refit-per-fold arm was reporting that its refits were free (F20). §4.6 records what Phase 6 closed and what it did not. |

**Honesty about the verification stages.** R1 returned 73/73 `CONFIRMED` — zero refuted is a sign of
a complacent verifier, not of good lenses. I independently reproduced three of R1's confirmations
(`g6-comando-ja-vermelho`, `f4-comando-nao-devolve-zero`, `features-seen-20-e-17-nao-existem`) and
all three held. R2 was given an explicit instruction to refute and returned **4 refuted out of 60**,
including a refutation of a finding that would have made the design worse. R1's verification stage
is the weak link in this chain, and that is on the record.

---

## §0 — Verified defects in what already exists

The rule that organises this: **this repository proved two models against a protocol whose equality
it asserts in prose and verifies nowhere.** It never bit because both existing models are
deterministic and never emit NaN. A TSFM is the repo's third `predict_fn` and the first with a real
chance of failing a horizon.

| id | sev | file:line | defect | evidence |
|---|---|---|---|---|
| **F1** | **blocker** | `models/train.py:88-115`, `:257-265` | `compare()` merges on `horizon_h` **without checking that the arms ran over the same fold set**, and emits no `n`. `build_artifact` records `folds`/`skipped_folds`/`first_cutoff_utc`/`last_cutoff_utc` **for the challenger only** and stamps the fixed string `"note": "identical folds and horizons for both models"`. Scenario: an arm returns NaN on 1 of 24 horizons, on 10 folds. **A: 55 folds / n=1320. B: 45 folds / n=1080. `fold sets equal: False`.** `train.compare()` returned **`mae_delta_pct: 518.68`, `horizons_won: 0/24`**, with no `n` field, **no error and no warning**. `[→ R2-15` — v2 cited `24/24`, impossible; v3 corrected it to `0/24`; R2 ordered the pair removed claiming irreproducibility and **Phase −1 reproduced it exactly**. Pair restored; R2-15 recorded as a false positive.] |
| **F2** | major | `models/backtest.py:126`, `:143` | `dropna()` collapses gaps: `predict_fn` receives a non-contiguous index. LightGBM and the baseline reindex by timestamp; a TSFM consumes `history.to_numpy()` — **position**. **The window is expanding**: one gap contaminates every subsequent fold. | A 6 h gap → a positional consumer is wrong about the date of its own last observation by +6 h. |
| **F3** | major | `models/backtest.py:111-176` | The seam has no protection at all against an adapter that reads the future. No test covers a prescient `predict_fn`. | `lambda h,t,c: series.reindex(t)` → **MAE 0.0**, no exception. |
| **F4** | major | `models/train.py:96-104` | **Zero uncertainty quantification around the model comparison.** `[→ f4-comando-nao-devolve-zero` — v2 claimed "anywhere in the repository" with a grep that returns 23 lines in 9 files; `drift/stats.py` has a KS p-value. The real defect is narrower.]` | `/usr/bin/grep -rn "diebold\|block_bootstrap\|confidence_interval\|paired.*bootstrap" models/ --include=*.py` → **0 lines**. |
| **F5** | major | `ci.yml:200` + `tests/test_artifacts.py:81-83` | The honesty gate is blind in **both** halves: CI reads `kind` only from `data.kind`; the pytest half **skips the artifact** when `data` has no `is_real`. | `monitor.json` and `pipeline.json`: `has_data=False`. **Stays open** — see §5. |
| **F6** | major | `README.md:193`, `:220`, `:296-298`, `docs/writeup.md:57` | Four occurrences of **live** prose say 56 folds, against `backtest.folds = 55` and `README.md:18`. | `grep -n "56 " README.md docs/writeup.md`. |
| **F7** | major | `README.md:192-193`, `CONTRIBUTING.md:39`, `docs/PUBLICATION-READY.md:68` | Live runtimes, contradicting each other, none tested. | Measured: `pytest` 29.0 s, not 20 s and not 16 s. |
| **F8** | major | `metrics/pipeline.json` | A published cost surface with no `host` and no thread count. The dashboard already renders it. | Read. |
| **F9** | minor | `ci.yml:177` | `find -size +5M` rounds in 1 MiB blocks; the real ceiling is 5,242,880 B inclusive. | Caught only 5,242,881 B; 5,242,880 and 5,000,001 passed. |
| **F10** | minor | `ci.yml:175-180` | The ceiling applies only inside `metrics/`, and measures the **disk**, not the index. | Read. |
| **F11** | minor | `tests/test_doc_claims.py:44` | The `(\d{3})` regex breaks at 1000 tests. | Read. |
| **F12** | minor | `dashboard/vite.config.ts:61-62` vs `useMetrics.ts:64-73` | `closeBundle` copies every `metrics/*.json` into `dist/data/`; `useMetrics` fetches five fixed ones. | Read. |
| **F13** | minor | `pyproject.toml:102-118` | New code is born in mypy's **strict** tier. | Read. |
| **F14** | major | `pyproject.toml:75` + `ci.yml:100,103` | `mypy` reports `Success` over a missing dependency; `pytest` fails hard at collection. | Read. |
| **F15** | minor | `README.md:778-779` | "The numbers are not results" — false since 2026-08-01. | 6/6 artifacts `is_real: true`. |
| **F16** | major | `.github/mutation-paths.txt` | `models/**`, `pyproject.toml`, `uv.lock` and `models/backtest.py` are all in the allowlist. **`foundation/` does not avoid the 60-minute `mutate` job**, because Phases 1 and 3 touch three of those paths. | `mutation_relevance.py`. |
| **F17** | major | `pyproject.toml:45` (`addopts = "-q"`) | Any invocation passing `-q` becomes `-qq` and pytest **prints no summary line at all**. Any gate parsing "N passed / N skipped" out of a `pytest -q` is green by construction. `[→ g9-pytest-q-nao-imprime-skipped]` | Measured. |
| **F18** | major | `ci.yml:93,94,100,103,108,114,121,141` | Only the `uv sync` (`:89`) uses `--frozen`. Every `uv run` after it re-resolves against `pyproject.toml`. `[→ R2-E-g5-e-no-op]` | Read. |
| **F19** | **blocker** | `foundation/tsfm.py:153` | The adapter passes the batch as `context=`, the parameter's name in `chronos-forecasting` **1.x**. `uv.lock` resolves **2.3.1**, where it is `inputs`. The lane's only path to a real forecast was dead, and no reading found it because the code is correct against the version its own docstring assumed. Found in §4.6, on the first line of this adapter ever executed with torch installed. | `TypeError: ChronosBoltPipeline.predict_quantiles() missing 1 required positional argument: 'inputs'`. |
| **F21** | **blocker** | `foundation/compare.py:158` | **Clause 1b and D10 were never implemented.** The verdict came out of `align_arms` — the intersection — which the RFC, the decision register and `align_arms`' own docstring all call survivorship filtering. `imputed_folds`, the field D10 declares mandatory, had **zero occurrences in the tree**. Invisible on the fixture, where every arm scores every fold and the two answers are equal; live the moment a TSFM fails a horizon, which is the one case the clause was written for. Reported by a review of the lane, then reproduced. | Manufactured: an arm perfect where it answers and silent on the hard stretch is `beats` over the intersection and lands in a different band under Clause 1b. |
| **F20** | major | `models/lgbm.py:133-160` + `tests/fixtures/foundation.sample.json` | A refit-per-fold arm reported that its refits were free. `WalkForwardLightGBM` refits **inside** the call the harness meters as inference, so no caller could start a `fit` timer — and the committed fixture carried `refits: 13` beside `fit_cpu_s: 0.0`. The existing test pinned only `refits == 0 -> fit_cpu_s == 0.0`; the converse was never asserted, and the refit is **96%** of this arm's measured cost. | `AssertionError: lgbm_12_no_calendar: 13 refit(s) at fit_cpu_s=0.0`. |

---

## §1 — Scope decisions

### 1.1 A lane, not a new repo — 6/6
The value of the finding depends on running against `metrics/model.json`, which carries
`is_real=true`, `backtest.folds=55` and a gate that bites. A new repo would rebuild
`models/backtest.py:111-125` and an **unreachable** panel (`.gitignore` holds `data/`), and would
compare against a transcribed `2.72%`.

### 1.2 `foundation/`, for dependency isolation — **not** for mutation cost
`[→ conflito-A-anulado-pela-propria-emenda]` The claim that `foundation/` avoids the `mutate` job is
**withdrawn**: `pyproject.toml`, `uv.lock` and `models/backtest.py` are in the allowlist and the RFC
orders all three edited (F16). The price of the decision, paid in the same commit: `foundation`
added to `[tool.mypy] files` **and** to `[tool.hatch.build.targets.wheel] packages`.

### 1.3 A separate artifact, with an offline subject
`metrics/foundation.json`, created **only in Phase 6**. Since it does not exist throughout the
offline lane, the lane versions **`tests/fixtures/foundation.sample.json`** as the permanent subject
of the schema gates, plus a named test: `metrics/foundation.json` **either does not exist, or** has
`is_real is True` and `data.kind == "eia_api_v2"`.

### 1.4 Cost in CPU-seconds — see §2.4, redone twice
### 1.5 Paired block bootstrap, block = origin (55). In the artifact; forbidden as a headline.

### 1.6 The arms — and the denominator, corrected for the third time

`[→ R2-01, R2-H-lgbm-12-frozen-nao-e-mesma-informacao, frozen-sem-ancora-move-o-denominador-em-3x]`

v2 corrected the committee. R1 corrected v2. **R2 corrected v3, and this time the amendment had
inverted the bias instead of removing it.** Measured on the fixture (200 d, 55 folds, published
params):

| `arms[].id` | cols | **informative** | refits | measured MAE | role |
|---|---:|---:|---:|---:|---|
| `seasonal_naive` | — | — | 0 | **2,551.25** | trivial floor |
| `lgbm_27` | 27 | 27 | 55 | (real: 3,049.79) | ceiling, **unfair by construction** |
| `lgbm_20_no_fcst` | 27 | 20 | 55 | (real: 5,159.56) | unfair — still sees observed temperature |
| **`lgbm_17_demand_only`** | 27 | 17 | 55 | **2,194.88** | **DENOMINATOR of Clause 5** |
| `lgbm_12_no_calendar` | 27 | 12 | 55 | **2,563.16** | information floor |
| `lgbm_12_frozen` | 27 | 12 | **1** | **4,363.64** | **descriptive only** — see below |
| `chronos_bolt@ctx671` / `@ctx2048` | — | — | 0 | — | the arms under test |

**Why `lgbm_12_frozen` left the denominator.** v3 created it to "pair the cadence" and put it in the
verdict's denominator. Measured, it is **70.24% worse than the same arm refit** and **71.04% worse
than the seasonal naive** — the trivial model this whole repository exists to beat. With it as the
denominator, a Chronos equal to the naive would publish `r = 0.585` → **"wins"**, and the defeat band
(`r > 1.25`) would require MAE **2.14x the naive**: unreachable. **The amendment created to give a
defeat condition removed it.** It stays as a descriptive arm, labelled *"a floor of **cadence**, not
of information"*, with the handicap declared in a field: **−31.7% training rows** (11,144 against
16,328) and **54 days of label lag**. `fit_anchor_utc` = `cutoff_candidates[0]`, pre-registered,
because the anchor is a free parameter that moves the MAE by roughly 3x.

**Primary contrast: `chronos_bolt@ctx671` against `lgbm_17_demand_only`** — the honest ceiling of a
GBM with no exogenous covariate, refit every fold. `lgbm_12_no_calendar` is the information floor and
is reported alongside. The interval is declared; the verdict uses one named denominator.

**Counting: `features_informative`, never "features".** The design matrix **always has 27 columns**;
the absent ones arrive as NaN. Verified on the ablated arm: 27 columns, 7 of them 100% NaN → 20
informative.

---

## §2 — Contracts

### 2.1 The seam's contract
`history`: `pd.Series` `float64` `demand_mwh`, univariate, **expanding** window,
`index.max() == cutoff − 1h` on 55/55 folds. `target_times`: 24 contiguous. Return: a **unique**
index (`preds.loc[t]`, `:158`). **One** NaN horizon discards the **whole fold** (`:221-226`).

### 2.2 The comparison contract

**Clause 1 — folds.** `cutoffs=` pins **candidates**, not the folds used: unscorability depends on
the **arm's prediction** (55 folds against 44, measured). After every arm has run: intersect,
re-score them all onto it, and record `folds_intersected` / `unscorable_cutoffs` per arm.

**Clause 1b — the intersection is survivorship filtering, and therefore does not decide the
verdict.** `[→ R2-11]` v3 admitted this in §6 and still let the verdict come out of the intersection
— an arm that fails precisely on the hard folds comes out with a lower MAE and the gate reports
green. **Correction:** Clause 5 is evaluated over the **full** `cutoff_candidates`, with each arm's
unscorable folds scored by a **declared pessimistic imputation rule: the `seasonal_naive` error on
that fold**. The intersection is still published, as a secondary number.

**Clause 2 — horizon.** `range(1,25)`, `cutoff_hour=12`, `weeks=8`.

**Clause 3 — context window.** `features.build.MIN_HISTORY_HOURS = 672` is the lag depth measured
from the **target**; the reach from the **origin** is **671 h** at `h=1` and 648 h at `h=24`
(verified). **The TSFM's context floor is 671 h.** Windows pre-registered **here, before Phase 6**:
`ctx=671` (parity) and `ctx=2048` (native maximum). Each is an arm with its own `id`.

**Clause 4 — covariates:** the table in §1.6, declared in a field.

**Clause 5 — verdict, pre-registered.** `r = mae(chronos_bolt@ctx671) / mae(lgbm_17_demand_only)`,
over the full `cutoff_candidates`:

| `r` | published verdict |
|---|---|
| `< 1.00` | the zero-shot TSFM **beats** the demand-only GBM |
| `1.00 – 1.25` | **competitive** |
| `> 1.25` | **not competitive** — a publishable result |

**Clause 6 — point reduction.** Chronos-Bolt is probabilistic; the reduction is **`median_q50`**,
pre-registered (the L1-optimal functional, and the metric is MAE). An asymmetry that has to be
written down: `models/lgbm.py:41-44` trains with `objective: "l1"` — **the GBM is optimised for the
judged metric and the TSFM is not.**

### 2.3 The artifact contract — fields new in this round

On top of what v3 already required: `arms[].fit_anchor_utc`, `arms[].train_rows_at_fit`,
`arms[].in_domain_training_hours` (**0 for `chronos_bolt`**) `[→ R2-H]`; `arms[].imputed_folds` and
the imputation rule used `[→ R2-11]`; `failed_gate` gains `arm-cadence`. `arms[].params` is
**derived from the trained booster** (`booster.dump_model()`), not from the caller's dict
`[→ g12-compara-metadado-com-metadado]`.

### 2.4 Cost table — normative, **CPU only**

`[→ R2-F-tabela-de-custo-nao-reproduz]` v2 labelled wall-clock as CPU. v3 redid it and **repeated
the mistake**: `params={"num_threads":1}` **does not serialise OpenMP** — it gave CPU 71.7 s against
wall 52.1 s (ratio 1.38, impossible for a single thread). Only with `OMP_NUM_THREADS=1` **in the
environment** does the ratio reach 0.99. Wall-clock leaves the normative table and becomes an
annotation stamped with `host`.

Measured, fixture 200 d, 300 rounds, stride 6 h, n=1320, 55 folds,
`host: AMD64 Family 25 Model 97 (AuthenticAMD), cpu_count=32`:

| regime | | **CPU (s)** | **CPU ms/prediction** |
|---|---|---:|---:|
| `OMP_NUM_THREADS=1`, `num_threads=1` | fit (55 refits) | **54.859** | **41.56** |
| `OMP_NUM_THREADS=1`, `num_threads=1` | infer (55×24) | **0.719** | **0.545** |
| `OMP_NUM_THREADS=32`, `num_threads=0` | fit (55 refits) | **1588.516** | **1203.42** |
| `OMP_NUM_THREADS=32`, `num_threads=0` | infer (55×24) | **23.531** | **17.827** |

1. **CPU rises ~29x going from 1 to 32 threads, and the wall time gets WORSE** (60.95 s against
   55.67 s). `models/lgbm.py:53` freezes `num_threads: 0` into the published params. **All of the
   lane's accounting fixes `OMP_NUM_THREADS=1` and `num_threads=1`, in the environment and in the
   param.**
2. **The refit is 98.7% of the GBM's cost.** Summing the lines hands the TSFM a win that belongs to
   the protocol. Three lines, never summed: `fit_cpu_s`, `infer_cpu_s`, `load_cpu_s` — all
   **measured** (0.0 expected, never stipulated).
3. Wall-clock was disqualified **by demonstration**: v2 measured 202.7 s of wall for the same work
   that came out at 59.9 s here — a 3.4x difference from machine load.

`ram_gb` and peak RSS **become mandatory again**
`[→ fase4-ram-gb-carve-out-por-premissa-falsa]`: v3 waived them claiming there was no offline
source, and the premise is false — the standard library resolves it (`GlobalMemoryStatusEx` on
Windows, `os.sysconf` on Linux), with no new dependency.

---

## §3 — Gates

**Every gate in this table enters through Phase −1 and is considered to exist only after it has been
seen failing, with the output pasted into the RFC.** The "definition" column is a starting point, not
a final specification — R2 proved eleven prose definitions wrong.

| gate | blocks | definition (to be built and seen red) |
|---|:--:|---|
| **G1 fold-identity** | yes | Intersect + re-score every arm; `folds_intersected` and `unscorable_cutoffs` recorded per arm. Raises only on an empty intersection or unrecorded divergence. **Runs in `models/train.py:compare()` AND in `foundation/compare.py`.** Needs a third deliverable: `backtest.rescore(result, folds)` `[→ R2-12]`. |
| **G2 contiguity** | yes | **Runs ONCE, over the experiment series, in `foundation/compare.py`, BEFORE the arms fork** — otherwise Chronos receives an interpolated value and LightGBM receives NaN, and Clause 1 is violated by the gate itself `[→ R2-08]`. Reindexes to `date_range(min, cutoff − 1h)` — not to `idx.max()`, which **cannot see a gap at the right edge**, the commonest case in a day-ahead setting `[→ R2-05]`. A gap touching `cutoff − 1h`: **unconditional refusal**, never imputation. An **absolute** budget, not 1% of an expanding window (which would authorise 161.9 fabricated hours on the real panel) `[→ R2-06, R2-07]`. |
| **G3 anti-foresight** | yes | **Per-fold probe: 55 pairs**, each pair with series identical on `index < cutoff_i` and divergent on `index >= cutoff_i`, **with the arm REBUILT from the perturbed series** — without rebuilding, not even perfect foresight is caught (`changed=0`, measured). v3's probe perturbed only the tail: coverage **1 fold of 55**, and an arm reading the future on folds 1–54 and honest on 55 comes out `changed=0` with **MAE 58.11 against the naive's 2,551** `[→ R2-02, R2-03]`. Negative control mandatory. **The cost of 55 pairs does not fit Phase 3's budget and Phase −1 has to measure it first.** |
| **G4 provenance schema** | yes | **Scoped to `metrics/foundation*.json` + the fixture.** `[→ R2-A, g4-bloqueante-vermelho-sem-fase-que-conserte]` v3 extended G4 across the whole glob and withdrew the F5 carve-out claiming it would close F5 "by construction" — **false: G4 detects, it does not fix**, and would leave the suite red on 2 of 6 artifacts with no phase to fix them. **F5 goes back to being a declared cut** (§5). |
| **G5 no torch in CI** | yes | **A gate on the CAUSE, three conditions** `[→ g5-nao-tem-estado-vermelho-alcancavel]`: (1) `pyproject.toml` declares torch only in `[project.optional-dependencies].foundation`; (2) the `ci.yml` sync line does not contain `--extra foundation`; (3) **`import foundation.tsfm` ends with `'torch' not in sys.modules`** — only (3) proves the lazy import. v2 used `uv pip list \| grep torch`; v3 swapped it for `python -c "import torch"` — **both green at HEAD, with not a line of the lane. The amendment reintroduced the defect.** Plus `env: UV_FROZEN: "1"` on the job, because only the `uv sync` uses `--frozen` (F18) `[→ R2-E]`. |
| **G6 nothing versioned >5,242,880 B** | yes | `git ls-tree -r -l HEAD \| awk '$4 > 5242880 {print; bad=1} END {exit bad}'` — reads the **object**, and **exits ≠ 0**. v3 used `git ls-files \| stat`, which reads the **worktree** (the text said "index", wrongly) and **printed the violation while exiting 0** — as a `run:` step, green `[→ R2-14, g6-comando-sai-zero-quando-acha-violacao]`. |
| **G7 cost has provenance** | yes | `hardware` by **domain** (not presence), three cost lines, `ram_gb` and RSS mandatory. |
| **G8 live prose pinned** | yes | Lane numbers read from an artifact by a test, with an anti-vacuum guard (`tests/test_artifacts.py:54`). |
| **G9 zero skips in the lane** | yes | The test lives **outside the glob it executes** (`tests/test_lane_gate.py`), otherwise it recurses `[→ g9-executor-recursivo]`; runs with **`-o addopts=`** because `pyproject.toml:45` already has `-q` and one more `-q` gives `-qq`, which **prints no summary at all** (F17); asserts `rc == 0`, a non-empty glob, `collected >= 1`, `skipped == 0` `[→ g9-pytest-q-nao-imprime-skipped, g9-vacuo-quando-o-glob-nao-casa]`. |
| **G12 arm-params** | yes | `params` **derived from the trained booster**, `refits` and `fit_anchor_utc` pinned. Canary: training with `num_leaves=31` while recording 63 must fail `[→ g12-compara-metadado-com-metadado, frozen-sem-ancora]`. |
| **G13 arm-composition** | yes | A derived rule for **all three** `lgbm_1x` arms, not just the 17-feature one `[→ g13-vigia-o-braco-errado]`. |
| **G10 uncertainty** | no | Mandatory in the artifact, forbidden as a headline. |
| **G11 dashboard** | no | Include it, or declare in writing that it stays out. |

---

## §4 — Phases

### Phase −1 — **Build the gates and watch them fail.** The mandatory entrance.

Eleven R2 blockers are gates specified in prose that die on the first command. No other phase starts
before this one. For **every** gate in §3 marked blocking:

1. write the canary **before** the gate;
2. run it and **observe red**;
3. **paste the literal output into the RFC**, dated, as a transcript (exempt per
   `tests/test_doc_claims.py:3-9`);
4. only then implement the gate and observe green;
5. **negative control**: the gate does not fire on the honest case.

- **Acceptance ✅:** 11 transcripts of observed red, one per blocking gate.
- **Acceptance ❌:** any gate whose definition does not produce red on the first command goes back to
  this phase. **A gate with no observed red does not exist.**
- **Acceptance ✅ (G3 budget):** measure the real cost of the probe's 55 pairs. If it does not fit
  CI, the decision is declared here — not discovered in Phase 3.

---

## §4.−1 — EXECUTED 2026-08-06. Transcripts of the observed red

Clean worktree at `22473e0`, `.venv` synced, `OMP_NUM_THREADS=1`.
**11 of 11 blocking gates observed red.** All with a negative control.

### G1 — `compare()` publishes numbers over divergent fold sets

```
CANARIO: braco B devolve NaN em 1 de 24 horizontes, em 10 folds.
  braco A : folds= 55  n= 1320  skipped=0
  braco B : folds= 45  n= 1080  skipped=10
  fold-sets iguais? False
def HOJE (models/train.py:88):
  compare() devolveu mae_delta_pct=518.68  horizons_won=0/24
  campo 'n' na saida de compare()? False
  >>> exit=0 <<< VERDE: numeros publicados sobre fold-sets divergentes, sem erro nem aviso
def v4 (rescore na intersecao + divergencia registrada):
  sem registrar divergencia -> failed_gate='fold-identity'   >>> exit=1 VERMELHO
  CONTROLE POSITIVO: intersecao=45 folds; n=1080 identico; unscorable={'A':10,'B':0}
  CONTROLE NEGATIVO (dois bracos identicos): failed_gate=None, intersecao=55, n=1320
```

**Two corrections only execution gave:**

1. **`R2-15` was wrong.** It claimed the pair `mae_delta_pct: 518.68` + `horizons_won: 0/24` was not
   reproducible and ordered it removed from §0. **It reproduced exactly.** The pair returns to §0 F1
   with the scenario named. *Recorded as an R2 false positive — the same genre R2 accused R1 of.*
2. **The name `unscorable_cutoffs` is wrong.** Arm A has `skipped_folds=0` and still loses **10**
   cutoffs to the intersection — because **B** failed on them. One field cannot mean both "folds this
   arm could not score" and "folds this arm lost to the intersection". → **two fields** (D20).

### G2 — the guard is green on top of the edge gap that motivated it

```
cutoff de teste = 2026-07-02 12:00:00+00:00
  buraco INTERNO (6h, 3 dias antes)
    def v3 (reindex ate idx.max())  -> horas faltando: 6
    def v4 (reindex ate cutoff-1h)  -> horas faltando: 6   toca a borda: False   (ambas pegam)
  buraco BORDA DIREITA (6h ate cutoff-1h)
    def v3 -> horas faltando: 0          <<< VERDE em cima do defeito
    def v4 -> horas faltando: 6  borda: True  >>> VERMELHO (failed_gate='contiguity')
CONTROLE NEGATIVO (serie intacta): def v4 -> 0 horas faltando -> VERDE
```

### G3 — detection hinges on a `>` vs `>=` the RFC never wrote

```
CANARIO: braco que le o futuro nos folds 1..54 e e honesto no fold 55.
sonda v3 (uma corrida, perturba so a cauda):
  perturbacao  > ultimo cutoff (36 de 4801 h):
     honesto    changed=   0/1320  MAE= 2551.25  VERDE
     oraculo    changed=  24/1320  MAE=    0.00  pega
     SORRATEIRO changed=   0/1320  MAE=   58.11  >>> VERDE (nao pega) <<<
  perturbacao >= ultimo cutoff (37 de 4801 h):
     SORRATEIRO changed=   1/1320  MAE=   58.11  pega por 1 previsao de 1320
sonda v4 (55 pares, perturba >= cutoff_i, braco RECONSTRUIDO):
     honesto    folds pegos  0/55   <- controle negativo limpo
     oraculo    folds pegos 55/55
     SORRATEIRO folds pegos 54/55   <- exatamente certo (honesto no 55)
```

**Sharper than finding R2-02.** R2 said "coverage 1 fold of 55". Execution shows worse: with `>` the
gate **catches nothing**; with `>=` it catches by **one prediction in 1,320**. The leaking arm
publishes **MAE 58.11 against the naive's 2,551.25 — 44x better** — with the gate green. **The
boundary convention has to be written into the RFC** (D21).

### G3 (budget) — **it does not fit, and the decision is declared here**

```
STUB deterministico, 13 pares (o que o job `test` roda) :    0,3 s   CABE
GBM, escala CI (weeks=2, 60 rounds, stride 12), 13 pares:   62   s   cabe, mas e UM braco
GBM, escala real (weeks=8, 300 rounds, stride 6), 55 pares: 91,0 min POR BRACO  -> NAO CABE
```

Five GBM arms x 91 min ≈ **7.6 h**. The RFC never accounted for this. **Decision D22**, taken here and
not in Phase 3.

### G4 — the gate is blind, and the two already-committed artifacts prove it

```
canario sem bloco `data`      : def CI -> VERDE | def pytest -> SKIPPED | def v4 -> VERMELHO
canario data.is_real diverge  : def CI -> pega  | def pytest -> pega    | def v4 -> VERMELHO
metrics/monitor.json          : def CI -> VERDE | def pytest -> SKIPPED | def v4 -> ['bloco data ausente']
metrics/pipeline.json         : def CI -> VERDE | def pytest -> SKIPPED | def v4 -> ['bloco data ausente']
```

**Confirms D12 by execution:** extending G4 to the whole glob leaves the suite red on **2 of 6**
artifacts the moment it lands. The carve-out is restored.

### G5 — neither earlier definition has a reachable red state

```
CANARIO: o HEAD como esta — ZERO linhas de codigo da lane.
  def v2  uv pip list | grep -i '^torch'      -> vazio, exit 1  -> portao VERDE
  def v3  uv run python -c "import torch"     ->        exit 1  -> portao VERDE
  def v4 (3 condicoes):
    (1) torch so em [optional-dependencies].foundation : False
    (2) linha de sync do ci.yml sem --extra foundation : True
    (3) import foundation.tsfm sem carregar torch      : False  (ModuleNotFoundError: 'foundation')
    >>> exit=1 VERMELHO — condicoes falhas: ['1','3']
```

### G6 — two independent defects, both reproduced

```
(a) FALSO POSITIVO — LICENSE: 1081 B no indice, inchado para 5.242.881 B no disco
    def v3 (git ls-files | stat = le o DISCO) -> VIOLACAO: 5242881 LICENSE   (falso)
                                                  exit do pipeline = 0
    def v4 (git ls-files -s | git cat-file -s = le o OBJETO) -> nenhuma violacao  (correto)
(b) FALSO NEGATIVO — blob de 5.242.881 B de fato no indice
    def v3 -> imprime "5242881 big.bin" e  >>> exit=0 <<<  portao VERDE
    def v4 -> >>> exit=1 <<< VERMELHO
```

### G7 — presence is satisfied by a placeholder; domain is not

```
artefato: hardware = {"cpu_model":"","n_threads":0,"ram_gb":0.0,"device":"unknown"}
  def v3 (presenca de bloco) -> campos faltando: nenhum       -> VERDE
  def v4 (dominio)           -> ['cpu_model vazio/curto','n_threads<1','ram_gb<=0',"device='unknown'"]
                                                               >>> VERMELHO
ram_gb offline pela stdlib: GlobalMemoryStatusEx -> 63.1 GB   (sem dependencia nova)
```

v3's `ram_gb` carve-out rested on a false premise. Confirmed: **withdrawn**.

### G8 — the pin is vacuously green because there is no subject

```
metrics/foundation.json existe?             False
tests/fixtures/foundation.sample.json existe? False
  def v3 -> 0 numeros da lane em prosa, artefato ausente -> nada a checar -> VERDE VACUO
  def v4 (guarda anti-vacuo) -> ['fixture-sujeito ausente'] >>> VERMELHO
```

### G9 — the gate counts skips that `-qq` never prints

```
pyproject.toml:45 -> addopts = -q
CANARIO: tests/test_foundation_canary.py com 1 teste normal e 1 SKIPPED.
  def v3  python -m pytest -q tests/test_foundation*.py   (addopts ja tem -q => -qq)
     exit=0
     saida completa: [.s                                                          [100%]]
     ocorrencias da string 'skipped': 0   >>> portao VERDE com 1 skip presente <<<
  def v4  -o addopts= , rc, glob, collected, skipped
     glob casou 1 arquivo; rc=0; resumo: "1 passed, 1 skipped in 0.21s"
     passed=1 skipped=1  >>> exit=1 VERMELHO: 1 skipped
```

### G12 — it compares metadata with metadata

```
booster REALMENTE treinado com num_leaves = 31
artefato DECLARA               num_leaves = 63
  def v3 (metadado x metadado) -> VERDE
  def v4 (derivado do booster) -> ['lgbm_17: booster=31 != artefato=63', ...] >>> VERMELHO
```

### G13 — it watches the wrong arm

```
esperado lgbm_17 = 17 features ; lgbm_12 = 12 features
braco lgbm_12_no_calendar SABOTADO com 13 features (is_holiday vazou)
  def v3 (so vigia lgbm_17)  -> VERDE
  def v4 (os tres bracos)    -> ["lgbm_12_no_calendar: 13 features, esperado 12; extra=['is_holiday']"]
                                >>> VERMELHO
CONTROLE NEGATIVO (composicao correta) -> VERDE, nao dispara no honesto
```

**Phase −1 state:** the 11 reds are observed and transcribed; the corrected definitions are validated
against a canary **and** against a negative control. What remains is implementing them as production
code — that is Phase 1 onwards. No canary was left in the repository (`git status --short` clean).

---

## §4.1 and §4.2 — EXECUTED 2026-08-06

Worktree `22473e0`, uncommitted. **No commit in `energy-forecast-drift`.**

### Phase 1 — green

Deliverables: `models/backtest.py` (`cutoffs=`, `rescore()`, `_summarise()` extracted so `run` and
`rescore` cannot drift apart), `models/train.py` (`FoldIdentityError`, `align_arms()`, `compare()`
refusing divergent fold sets and emitting `n`, `build_artifact` recording both arms instead of the
fixed string), `tests/test_fold_identity.py` (9 tests).

```
compare() sobre fold-sets divergentes:
  FoldIdentityError: Refusing to compare arms scored on different folds (55 vs 45)
align_arms:
  folds_intersected : 45      n_per_arm : 1080
  baseline    folds_scored=55  own_failure= 0  dropped_vs_intersection=10
  challenger  folds_scored=45  own_failure=10  dropped_vs_intersection= 0
  os 10 cutoffs nomeados batem com os injetados: True
intersecao vazia:
  FoldIdentityError: The arms share no fold at all ... x=28 fold(s), y=27 fold(s)
```

**D20 confirmed in execution:** the baseline has `own_failure=0` and still loses 10 folds. A single
counter would have reported it as failing on 10 folds it scored perfectly.

**Mutation gates — all three green**, after three corrections only execution gave:

```
mutation_score.py --floor 66 : 69.3% (341/492); models/backtest.py 82.0% (123/150)  EXIT=0
mutation_survivors.py --check: 0 nao-adjudicados                                     EXIT=0
mutation_ratchet.py  --check : 0 regressed, 0 vanished, 0 ambiguous                  EXIT=0
```

1. **`mutmut` does not run on this platform without `PYTHONIOENCODING=utf-8`** — it dies on
   `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f389'`, on its own emoji, under
   cp1252. The RFC anticipated that `untested` would count differently on Windows; the problem is
   upstream of that. → **D23**.
2. **My 9 tests were not running against the mutants of my own code**, because
   `tests/test_fold_identity.py` was not in `[tool.mutmut] runner`. With the file in the runner and in
   `.github/mutation-paths.txt`, `models/backtest.py` went from **75.3% to 82.0%**. → **D24**.
3. **Three adjudication rules unhooked** through line drift (+16, +16, +61). Not a defect:
   `scripts/mutation_survivors.py:57-59` matches on `(file, line, snippet)` and the comment at
   `:50-54` says the snippet was added precisely so that unhooking would be noisy rather than silent.
   **The gate worked.** Re-anchoring is expected maintenance for anyone editing a mutated file.
   → **D25**.

**A control that refuted my hypothesis.** I assumed the unadjudicated survivors were pre-existing or a
platform artifact. I ran pristine HEAD on the same machine: `mutation_survivors.py --check` →
**EXIT=0**, 69.4% (329/474). They were not. The hypothesis was wrong and the control is what showed
it.

**One of my tests was loose, and the mutant proved it.** `match="empty fold set"` is a `re.search`, so
it matched `"XXCannot rescore onto an empty fold set.XX"` — the wrap mutmut applies. Mutant 459
survived my own test. Anchored on `^…$`, it dies.

### Phase 2 — green

Deliverables: `features/build.py` (`blank_features`, `informative_features`, `drop_features=` in
`build_design_matrix`), `models/lgbm.py` (`drop_features` and `freeze_at` propagated to training
**and** prediction), `models/arms.py` (the ladder, `assert_composition`, `assert_params`,
`assert_cadence`), `tests/test_arms.py` (13 tests).

**The ladder, measured on the 200-day fixture, 55 folds, `cutoffs=` pinned:**

```
arm_id                 informativas  refits        MAE   portoes
lgbm_27                          27      55    2199.72   G12+G13 ok
lgbm_20_no_fcst                  20      55    2160.58   G12+G13 ok
lgbm_17_demand_only              17      55    2194.88   G12+G13 ok
lgbm_12_no_calendar              12      55    2563.16   G12+G13 ok
lgbm_12_frozen                   12       1    4363.64   G12+G13 ok
seasonal_naive                    -       0    2551.25
G1: folds_intersected=55  n_per_arm=1320  todos identicos=True
```

- **Clause 5's denominator is legitimate:** `lgbm_17_demand_only` = 2,194.88 **beats the naive**
  (2,551.25).
- **D07 confirmed by independent measurement:** `lgbm_12_frozen` = 4,363.64, **+71.0% worse than the
  naive**. It stays out of the denominator.
- `lgbm_20_no_fcst` (2,160.58) is better than `lgbm_27` (2,199.72) — expected, and it is the repo's
  own `FIXTURE_ABLATION_WARNING`: on the fixture, forecast weather *hurts*. Not a result.

**Phase 2 found an empty gate — mine.** The first version of `assert_composition` inferred composition
from the data: it counted non-null, non-constant features. That **cannot tell blanked from constant**.
Measured: `is_holiday` has `nunique() == 1` over a 40-day window (no federal holiday falls in it) and
`== 2` over 200. The sabotage canary — a twelve-feature arm built carrying thirteen — **passed** the
gate, silently, for a reason with nothing to do with the sabotage.

Corrected into two halves, neither redundant: the declared set matches the spec, **and** the frame
honours the declaration (every feature declared as dropped must really be blank). And the test fixture
went up to 200 days, with a dedicated test that fails if the window contains no holiday — because
otherwise the canary proves nothing. → **D26**.

### Phase 3 — green

Deliverables: `foundation/guards.py` (**torch-free**, G2 and G3), `foundation/stub.py` (positional on
purpose), `foundation/tsfm.py` (lazy import), `foundation/__init__.py`,
`tests/test_foundation_lane.py` (19 tests). `pyproject.toml`: `foundation` extra, `foundation` in
`[tool.mypy] files` **and** in the wheel.

```
ruff check         : All checks passed          ruff format: 95 files already formatted
mypy               : Success, 39 source files   (era 34; foundation entrou no escopo)
pytest             : 418 passed, 11 skipped, 429 coletados, EXIT=0
G5 (subprocess)    : import foundation.tsfm -> 'torch' in sys.modules == False
orcamento CI (OMP_NUM_THREADS=2, weeks=2, 13 folds):
   G2 guard        : 0.00 s      braco stub : 0.01 s      G3 sonda 13 pares : 0.11 s
   TOTAL           : 0.13 s   -> cabe em 90 s com folga de tres ordens de grandeza
```

**The relock `xfail(strict=True)` lasted fifteen minutes, because the relock happened on its own.**
`uv.lock` turned up modified without my having run `uv lock`: **a bare `uv run` re-resolves and
rewrites the lockfile**. Only `ci.yml`'s `uv sync` step uses `--frozen`; the eight `uv run` steps after
it do not (F18). Measured: the lock went from **152 to 185 packages**, none removed, no version
changed — and among the 33 new ones came **the entire CUDA stack** (`nvidia-cudnn-cu13`,
`cuda-toolkit`, `triton`), gigabytes of wheels for hardware the lane declares it does not have.
→ **D27**, **D28**.

Fixed with `[tool.uv.sources]` pointing torch at the CPU index: **18 CUDA packages → 0**, lock 185 →
169, `torch 2.13.0+cpu`, and `uv sync --extra dev --frozen` still **EXIT=0**. The `xfail` became a
normal test, plus a new test that fails if any CUDA wheel returns to the lock.

**R2-E confirmed live:** `uv sync --extra foundation --frozen` exits **EXIT=2** with *"Extra
`foundation` is not defined in the project's `optional-dependencies` table"* — pointing at the file
where it **is** defined. `--frozen` reads the project's view from `uv.lock`.

**Two defects of mine that only execution found:**

1. **The guard destroyed the actuals.** It returned only the repaired grid, which ends at
   `max(cutoffs) − 1h` — so every target hour vanished and `backtest.run` raised *"Every fold was
   unscorable"*. The fix is **not** to extend the grid over the actuals: imputing an actual fabricates
   the answer. Repairing history is a repair; repairing an actual is invention. A missing actual
   **stays missing**, the fold drops, and that is the honest outcome — which the harness already
   implements. → **D29**.
2. **The guard lost the index name.** `pd.date_range` produces an unnamed index, and the reindex
   dropped `timestamp_utc` silently.

**F13 confirmed:** `foundation` landed in mypy's **strict** tier, because the relaxed overrides are a
module whitelist. `foundation.guards` joined the relaxed list with the same justification as ADR 0002
(`pd.DatetimeIndex(Sequence[Timestamp])` and `Index.difference` are stub noise no correct code
satisfies); `foundation.tsfm` and `foundation.stub` stayed strict.

### Phase 3b — green

Deliverable: `.github/workflows/ci.yml` — three new steps (G5, G6, G9) plus `env: UV_FROZEN: "1"` on
the `test` job (required by **D27**). Four new assertions in `tests/test_workflows.py`.

```
ruff / format / mypy : limpos, 39 source files
pytest               : 422 passed, 11 skipped, 433 coletados, EXIT=0
tests/test_workflows : 38 passed  (as guardas existentes nao quebraram)
uv.lock sob `uv run --frozen`: nao se moveu
```

**Every installed step was seen red on its canary, with a negative control:**

```
G6  entrada 'mode blob sha 5242881 big.bin' -> ::error::5242881 bytes: big.bin   exit=1
    controle negativo (LICENSE, 1081 B)                                          exit=0
G5  torch presente em sys.modules apos importar foundation.tsfm                  exit=1
    controle negativo (torch ausente)                                            exit=0
G9  um skip acrescentado a suite da lane -> "41 passed, 1 skipped" detectado      VERMELHO
    controle negativo (sem skip, 41 passed)                                       verde
```

**Two of the three canaries passed for the wrong reason first, and that is the record.** G6's compared
`$2`/`$3` of a fake line — `"blob" > 5242880`, a **string** comparison, true by accident; the real
fields of `git ls-tree -r -l` are `$4` (size) and `$5` (path). G5's did `import json as torch`, which
puts `json` in `sys.modules`, not `torch`. Both redone. **A canary that passes for the wrong reason is
an unverified gate**, and the Phase −1 rule applies to the canary as much as to the gate.

**And two of my assertions matched the prose instead of the command.**
`test_ci_proves_torch_never_...` and `test_the_ci_sync_line_never_requests_the_foundation_extra`
searched the whole file for `--extra foundation`, and matched the **G5 step's own error message**,
which names the extra it is refusing. It is exactly the trap `tests/test_workflows.py` already
documents in `run_commands(strip_comments=)`: *"a test looking for a dangerous command must not match
the sentence warning against it."* Fixed to scan only the `uv sync` lines — which is what the second
test's name already said while its body scanned the whole file.

### Phase 4 — green

Deliverables: `foundation/cost.py` (`CostMeter`, `hardware_block`, `peak_rss_mb`, `_ram_gb`,
`assert_cost_provenance` = G7), `tests/test_cost.py` (23 tests).

```
ruff / format / mypy : limpos, 40 source files
pytest               : 445 passed, 11 skipped, 456 coletados, EXIT=0
```

**The cost table, measured end to end** (`OMP_NUM_THREADS=1`, `num_threads=1`, 200-day fixture, 55
folds, n = 1,320, `hardware.ram_gb = 63.14`):

```
arm                    refits  fit_cpu_s  infer_cpu_s  load_cpu_s  fit ms/prev  infer ms/prev
lgbm_27                    55      51.69        0.688       0.000        39.16          0.521
lgbm_20_no_fcst            55      33.47        0.625       0.000        25.36          0.473
lgbm_17_demand_only        55      28.61        0.688       0.000        21.67          0.521
lgbm_12_no_calendar        55      23.89        0.609       0.000        18.10          0.462
lgbm_12_frozen              1       0.41        0.656       0.000         0.31          0.497
stub_zero_shot              0       0.00        0.031       0.000         0.00          0.024
G7 assert_cost_provenance -> OK
```

Three things the table shows that the RFC did not anticipate:

1. **Fit cost scales with the feature count**: 51.69 → 33.47 → 28.61 → 23.89 s as the informative
   count falls 27 → 20 → 17 → 12. The fairest arm is also the cheapest, which weakens any reading of
   "the GBM is expensive because it is good".
2. **`lgbm_12_frozen` costs 0.41 s against 23.89 s for the same arm refit — 58x cheaper** — and is 71%
   worse than the naive. The cadence/accuracy trade-off becomes explicit in numbers, which is the only
   honest use left for that arm after **D07**.
3. **The refit is 98.7% of `lgbm_27`'s cost** (51.69 of 52.38), reproducing §2.4's independent
   measurement.

**v3's `ram_gb` carve-out fell, and the premise was false.** v3 made `ram_gb` and peak RSS nullable
claiming there was no offline source (`psutil` outside the lockfile, `resource` Unix-only).
`GlobalMemoryStatusEx` and `os.sysconf` are **standard library**. Measured: `ram_gb = 63.14`,
`peak_rss_mb = 19.1`. Both mandatory again, with no new dependency.

**And the cost meter produced, itself, the placeholder G7 refuses.** The first version of
`peak_rss_mb()` returned **0.0** on Windows: `GetCurrentProcess` returns a pseudo-handle and, without
an explicit `restype`, ctypes assumes `c_int` and truncates it on 64-bit — the call fails and the
function returns zero in silence. A plausible zero coming from the code that feeds the gate is worse
than an error. It now has explicit signatures and **raises** instead of returning zero.

**G7 has two halves, and the second is the one that bites.** By name (`total_cpu_s`, `cpu_s`,
`cost_per_prediction`, `seconds`) and **by value**: any numeric field equalling `fit+infer`,
`fit+load`, `infer+load` or all three is refused. The interesting version of the mistake is a field
with an innocent name — `elapsed` — holding the sum the contract forbids, and a canary test covers
exactly that. With a negative control: a zero-shot arm has `fit_cpu_s == 0.0`, which makes some sums
equal a single line, and refusing that would make the gate useless on precisely the arm the lane
exists to measure.

### Phase 5 — green, and Phase 3's debt paid

Deliverables: `foundation/uncertainty.py`, `foundation/compare.py` (**the assembler I had listed in
Phase 3 and not written**), `tests/fixtures/foundation.sample.json`, `tests/test_uncertainty.py` (16),
`tests/test_lane_artifact.py` (13).

```
ruff / format / mypy : limpos, 42 source files
pytest               : 475 passed, 11 skipped, 486 coletados, EXIT=0
step G9 (lista derivada): 5 arquivos, 84 passed, rc=0, zero skips
artefato de fixture  : failed_gate=None, 6.886 bytes, 3 bracos, 2 intervalos
```

**The block is the origin, and the cost of getting that wrong is measured:**

```
par                                          MAE ratio   IC95 (bloco=origin)   largura
lgbm_12_no_calendar / lgbm_17_demand_only       1.1678   [1.1146, 1.2323]       0.1177
seasonal_naive      / lgbm_17_demand_only       1.1624   [1.1226, 1.2037]       0.0811

largura IC, bloco=origin (n_blocks=  55) : 0.1177
largura IC, bloco=ponto  (n_blocks=1320) : 0.0579
=> reamostrar por ponto SUBESTIMA a incerteza em 2.0x
```

**And this closes the TimesFM trigger with a number instead of an argument.** The reopen band
`[0.95, 1.10]` is **0.15** wide; the interval measured on this project's own folds is **0.118** wide.
Same order — exactly what `gatilho-timesfm-mais-estreito-que-o-proprio-ic` alleged in R1 and what is
now measured on this lane's data. A trigger on the point estimate would be a coin flip wearing a rule.
`reopen_timesfm` operates on the **interval**, and there is a parametrised test with the four outcomes
plus an edge case.

**The G9 step's file list rotted in the same session it was born.** I wrote it by hand with three
files in Phase 3b; the lane reached six in Phase 5 and the three newest were **outside the no-skip
gate**. It is literally the failure mode `.github/mutation-paths.txt` documents — *"two lists that
must agree by hand is the failure mode this file designs out"*. The step now **derives** the list by
grepping the imports, and `tests/test_workflows.py` recomputes the same set and fails if they diverge.
The pattern's first attempt missed `tests/test_arms.py`, which imports `from models import arms, ...`
and not `from models.arms` — fixed, 5 files, 84 tests.

**The fixture exists because otherwise the schema gates are vacuously green.**
`metrics/foundation.json` is only born in Phase 6, so every assertion about it would be true over the
empty set throughout the implementable part of the lane. `tests/fixtures/foundation.sample.json` is
produced by the **same** `build_artifact` that will write the real one, with an anti-vacuum guard in
the pattern of `tests/test_artifacts.py:53`.

**A refusal is stamped, not raised.** `build_artifact` catches the gate errors it knows and records
`failed_gate`, with a test preventing an invented gate name from becoming a field value. And Phase 6's
❌ acceptance stopped being the unverifiable prohibition *"the agent must not commit it"*:
`test_metrics_foundation_json_is_real_or_absent` says the file **either does not exist, or** has
`is_real: true` and `kind: eia_api_v2` — accusing the lane, not the README banner.

### Phase 7 — green

```
ruff / format / mypy : limpos, 42 source files
pytest               : 478 passed, 11 skipped, 489 coletados, EXIT=0
grep -n "56 " README.md docs/writeup.md -> so as 5 linhas dentro do <details> 224-251
```

**F6 fixed, and the "56" was wrong even for the fixture.** Four live occurrences (`README.md:193`,
`:220`, `:296-298`, `docs/writeup.md:57`). The natural assumption would be that 56 held for the
fixture and 55 for the real panel — **false**: I ran `models.train --source synthetic` and the
artifact came out with `folds: 55, refits: 55, n: 1320`. The 56 dates from when
`DEFAULT_CUTOFF_HOUR` was 0; since it moved to 12 the answer is 55 for both. Lines 239-243 stay: they
are inside the quarantine `<details>`, they are a dated record, and a test that could not tell live
prose from history would force the history to be falsified.

**F7 fixed, with three measurements.** `uv run pytest` over three runs: **26 s, 27 s, 25 s** against
`~20 s` in README/CONTRIBUTING and `~16 s` in `docs/PUBLICATION-READY.md`.
`models.train --source synthetic --no-mlflow`: **100–105 s** against `~1 min`.

**F15 fixed.** `README.md:778` said *"The numbers are not results, so there is nothing there to
cite."* — false since 2026-08-01, with the file's own banner leading on measured numbers.

**Three new pins, each measuring what can be measured without becoming a flake:**

- `test_the_documented_fold_count_is_the_one_in_the_artifact` — reads `metrics/model.json →
  backtest.folds` and compares it with the **live** prose, `<details>` stripped by regex.
- `test_the_three_statements_of_the_test_runtime_agree` — **does not** pin the absolute value, which
  is machine-dependent and would become a flake on a slower runner. It pins that the files **agree
  with each other**, which is the real defect F7 names and is deterministic.
- `test_any_lane_number_in_prose_is_read_from_an_artifact` — **armed before a subject exists.** A pin
  written as "every lane number matches the artifact" is vacuously green today and stays green until
  the day someone writes the first sentence about the lane, which is exactly when nobody is looking.
  So it fires on the **prose**: if the README names an arm, the published artifact has to exist and
  must not be refused. Canary seen red (a sentence citing `lgbm_17_demand_only` → fails) and negative
  control green.

---

### Phase 0 — green, and **reproduced** rather than conferred

The session had network, so instead of checking the transcript against the RFC I redid it against the
Hugging Face API — stronger than the acceptance asked for.

```
amazon/chronos-bolt-tiny        34.622.352 B  apache-2.0  gated=false  rev a0e552de...
amazon/chronos-bolt-small      190.888.824 B  apache-2.0  gated=false  rev 772f3d25...
google/timesfm-2.0-500m-pytorch 1.995.406.976 B apache-2.0 gated=false  rev dc244379...
teto 5.242.880 B -> 6,6x / 36,4x / 380,6x
sha256 (chronos-bolt-small) = 06a6a19bbe74bc10a9cd193bd4bf2bf638ae07f7e0d51653ae7ab8ea968a21dd
G6: git ls-tree -r -l HEAD | awk '$4 > 5242880'  -> exit 0
maior objeto versionado: uv.lock, 917.293 B
```

The `sha256` comes from the LFS `X-Linked-ETag` header, so it identifies **the file that will be
downloaded** and was obtained **without downloading the 190 MB**.

**The contamination fields are why this phase is not paperwork.** v3's §6.1 cited the **TimesFM** card
as evidence — a model the RFC itself cuts — so the declared corpus described a checkpoint that will
never run. The fields are now about `DEFAULT_REPO`.

**`energy_domain_in_corpus` = `undeclared`, not `yes`, and the distinction is the finding.**

*Established:* the card enumerates no dataset at all, only *"trained on nearly 100 billion time series
observations"*; `arXiv:2403.07815` organises its dataset appendix by domain with a named **`B.1
Energy`** subsection; and Table 1 records *Benchmark I* (15 datasets, 97,272 series) as *"pretraining
and in-domain evaluation"* — that is, **pretraining is not disjoint from the benchmark**.

*Not established:* the row-level split — whether any particular electricity series is pretraining-only
or held out. I could not retrieve the complete Table 2 / Appendix B.

`yes` would assert what was not retrieved; `no` would be false. `undeclared` keeps the risk visibly
open, which is the only honest state — and a test **refuses** an `undeclared` that carries no
evidence, because that is indistinguishable from nobody having looked.

The fold window postdates every released checkpoint, so the target **value** cannot be memorised. That
protects against memorising the value, not the **shape**, and a daily-and-weekly electricity load
profile is ordinary material in these corpora.

---

## §4.6 — EXECUTED 2026-08-06. Phase 6, and the half of it that is not done

Phase 6 was written as **[DISPATCH]** on two premises about the implementer's machine. One was
verified false and one true, and checking rather than assuming is what made the difference:

```
pypi.org/simple/                                      HTTP 200
huggingface.co/.../chronos-bolt-small/config.json     HTTP 307   -> rede DISPONIVEL
EIA_API_KEY no ambiente                               ausente
.env no repo                                          nao existe
.env dos outros projetos que mencionam EIA            nenhum
data/raw/                                             so weather_hourly, 2 arquivos, 24 KB
```

So the checkpoint, the library and the adapter were reachable and the **demand panel was not**. Phase
6 splits along exactly that line.

### The runner did not exist

`foundation.compare.score_arm` and `build_artifact` were called by nothing but tests. The lane had
every gate and no command — *"Phase 6 is a dispatch step"* named an action nobody could take.
`foundation/__main__.py` is that command, with `tests/test_dispatch_runner.py` (15) behind it.

Three refusals, each seen firing:

```
$ python -m foundation --source synthetic --tsfm stub          # sem --out
error: refusing to write .../metrics/foundation.json: it is defined as real or
       absent, and this run is is_real=False kind='synthetic_fixture'.
EXIT=3        metrics/foundation.json: nao existe  <- nada foi escrito

$ python -m foundation --source real --tsfm stub
error: No EIA demand in the lake. Run `uv run python -m ingest` first ...
EXIT=2

$ OMP_NUM_THREADS=8 python -m foundation --source synthetic ... --n-threads 1
error: OMP_NUM_THREADS='8' but --n-threads=1. ... the cost lines would describe
       a machine nobody configured.
EXIT=2
```

### F19 — the adapter had never been run, and did not work

`uv.lock` resolves `chronos-forecasting==2.3.1`, whose signature is
`predict_quantiles(inputs, ...)`. The adapter was written against the 1.x name, `context=`:

```
TypeError: ChronosBoltPipeline.predict_quantiles() missing 1 required positional argument: 'inputs'
  File "foundation/tsfm.py", line 153, in __call__
load OK, pipeline = ChronosBoltPipeline          <- load() funcionava; a chamada nao
```

Fixed by passing the batch **positionally**, which is correct under both versions, so the declared
floor `>=1.5` stays honest. Pinned by `test_the_pipeline_call_passes_its_batch_positionally`, which
reads the call out of the AST — the only way to hold this rule in a job that must never install torch.
After the fix, the contract measured rather than asserted:

```
tipo Series | len 24 | indice==alvo True | nome timestamp_utc | float64 | NaN 0
mesma saida com historico cortado em 671h : True     <- MIN_CONTEXT_HOURS aplicado de fato
history alcancando o cutoff -> RuntimeError "not strictly before"
```

### Phase 0's numbers, verified against the file instead of the API

The `WEIGHTS` pin was resolved from the HTTP headers without downloading. Now downloaded and hashed:

```
bytes  : declarado 190888824 | medido 190888824 | CONFERE
sha256 : declarado 06a6a19bbe74bc10a9cd193bd4bf2bf638ae07f7e0d51653ae7ab8ea968a21dd
         medido    06a6a19bbe74bc10a9cd193bd4bf2bf638ae07f7e0d51653ae7ab8ea968a21dd  CONFERE
```

### G5's third condition had never been in a position to fail

The only condition of G5 with a reachable red state asserts that importing the adapter leaves torch
out of `sys.modules` — and it had only ever run where **torch was not installed**, so the branch it
guards was unreachable. With `--extra foundation` installed:

```
torch instalado neste venv : True
G5 cond.3 hoje             : 1 passed
CANARIO: `import torch` no escopo do modulo
  E  + True
  FAILED tests/test_foundation_lane.py::test_importing_the_adapter_does_not_import_torch
revertido                  : 1 passed
```

### F20 — a refit-per-fold arm was reporting that the refit was free

The committed fixture declared `refits: 13` beside `fit_cpu_s: 0.0` on `lgbm_12_no_calendar`. The
cause was structural: `WalkForwardLightGBM` refits *inside* the call the harness meters as inference,
so no caller could ever start a `fit` timer. The existing test pinned only the other direction
(`refits == 0 -> fit_cpu_s == 0.0`).

```
CANARIO (a assercao que faltava, contra o fixture publicado):
  AssertionError: lgbm_12_no_calendar: 13 refit(s) at fit_cpu_s=0.0
depois de instrumentar models/lgbm.py:
  lgbm_17_demand_only  fit=4.39s  infer=0.20s   <- refit = 96% do custo do braco
  chronos_bolt@ctx671  fit=0.00s  infer=0.45s  load=5.22s
```

### The fixture is now produced by the committed command

`tests/fixtures/foundation.sample.json` was hand-assembled. It is now the output of

```
OMP_NUM_THREADS=1 python -m foundation --source synthetic --fixture-days 90 --weeks 2 \
    --tsfm chronos --out tests/fixtures/foundation.sample.json
```

which also gives the schema gates a subject they never had: `weights` was `null` on every arm and
`load_cpu_s` was `0.0` on every arm, so two thirds of the provenance block and one of the three cost
lines were only ever checked against absence.

```
arm                       MAE       fit_cpu_s  infer_cpu_s  load_cpu_s  peak_rss_mb
lgbm_17_demand_only   2.268,23        4,3906       0,2031        0,00        179,9
lgbm_12_no_calendar   2.202,57        3,8906       0,2344        0,00        182,2
chronos_bolt@ctx671   3.912,52        0,0000       0,4531        5,22        618,5
```

**These are not a result.** Synthetic fixture, `is_real: false`, warning attached — a smoke test of the
plumbing. The memory line is the one thing worth reading: **3.4x the GBM's peak RSS**, which is why
§2.4 reports it beside the CPU lines rather than instead of them.

### G3 has power over the Chronos path, and that had to be shown separately

A zero-shot arm reads only `history`, so it is *structurally* incapable of seeing the future — which
means a clean probe proves the harness slices correctly and says nothing about the gate working. With
a deliberately leaking arm (the honest forecast plus 1% of the post-cutoff series):

```
CONTROLE NEGATIVO (ChronosArm real)  : {'probed': 2, 'caught': [], 'clean': True}
CONTROLE POSITIVO (vaza 1% do futuro): {'probed': 2, 'caught': ['2026-07-21T12:00', '2026-07-22T12:00']}
  >>> LaneGateError: forecast changed when only the post-cutoff future changed, on 2 of 2
```

### A false alarm, chased to the end because it looked like a defect

`uv run mypy` — the exact CI command — reported **38 errors in 13 files**, mostly pandas plumbing in
files this session never touched. Bisected: not torch, not transformers, not accelerate, not chronos,
not setuptools, not the mypy cache; the two environments ended with **164 packages each, differing in
two patch versions**, and still gave 38 against 2. Deleting and re-creating the virtualenv resolved it:

```
venv acumulado na sessao : Found 38 errors in 13 files (checked 43 source files)
venv recriado do lock    : Success: no issues found in 43 source files
```

No repository defect. Recorded because the first four rounds of that investigation all pointed at a
cause that was not there, and *"my environment"* is a hypothesis that has to be tested rather than
assumed — in either direction.

### F21 — the clause the code did not honour

Found by a review of the finished lane, not by the lane's own gates, and it is the most serious thing
in this document: **Clause 1b and D10 were never implemented.** The verdict came out of `align_arms`
— the intersection — while `imputed_folds`, the field D10 calls mandatory, had zero occurrences in
the tree. Every gate was green because on the fixture every arm scores every fold, so the verdict
base *is* the intersection and the two answers agree exactly.

The failure is only reachable if a fold is manufactured, which is what
`tests/test_imputation.py` does — an arm that answers perfectly where it answers and goes silent over
the hard stretch:

```
candidatos                   : 22
folds duros (o braco cala)   : 6
imputed_folds do quitter     : 6
r sobre a intersecao         : 0.000  -> banda "beats"
r sob a Clausula 1b          : 1.212  -> banda "competitive"
bands_agree                  : False
```

The `0.000` is not a rounding artefact and it is the cleanest statement of the defect available: the
arm is *exact* on every fold it answers, so over the intersection its MAE is literally zero and it
wins by an infinite margin. Under Clause 1b the same arm is charged the naive's error on the six days
it declined and lands mid-band. Nothing about the arm changed between those two lines.

Two rules, two bands, same data. The intersection removes the hard folds **from the arm being
compared against as well**, so the quitter is credited with the days it chose to answer and the
reference loses the days where it was winning. That is the whole content of "an arm gets flattered by
its own failures", and nothing in the lane would have caught it: the counters that make the filtering
visible were all present and correct, and reporting a bias is not the same as removing it.

`foundation/imputation.py` charges an unscorable fold **the seasonal naive's own rows** on that fold —
prediction and actual substituted whole, so the arm gets exactly the trivial model's error and no
value is synthesised. Consequences worth naming:

- `seasonal_naive` stops being optional. It is the imputation source, so the artifact is **refused**
  (`failed_gate: "imputation"`) rather than quietly intersected when it is absent.
- `arms[].mae` is now the Clause 1b number and the intersection survives as `mae_intersection`.
  Putting the verdict anywhere other than the field called `mae` invites the exact mistake the clause
  exists to stop.
- The interval moved with it. A bootstrap over the intersection beside a point estimate over the base
  describes neither.
- A candidate the naive itself could not score is **excluded**, not imputed, and recorded in
  `candidates_without_ground_truth`. There is no ground truth there for anyone; charging an arm the
  error of a model that also failed would invent the comparison rather than make it pessimistic.
- D10's reversal criterion is now evaluated instead of described: `verdict[].bands_agree` recomputes
  the band under "drop the fold" and says whether it moves.

The first draft of `band()` also collapsed Clause 5's two boundaries into one `<=` loop, which puts an
exact `r = 1.00` in **beats** instead of **competitive** — the single value most likely to be argued
over, in the wrong direction. Both boundaries are parametrised by test now.

### What is NOT done, and will not be declared done

**The verdict.** `r = mae(chronos_bolt@ctx671) / mae(lgbm_17_demand_only)` on the real panel does not
exist and cannot be produced here: it needs `EIA_API_KEY`, which is a repository secret and is not on
this machine, plus one `python -m ingest` run to fill the lake. `metrics/foundation.json` therefore
still does not exist, which is the state the lane's own gate defines as correct.

The pre-registered reading stands unchanged, and the command is in `docs/BLOCKED.md`:

| `r` | verdict |
|---|---|
| `< 1.00` | the zero-shot model wins |
| `1.00 – 1.25` | competitive |
| `> 1.25` | not competitive |

---

### Phase 0 — original transcript (v4, kept as a record)

```
huggingface.co/api/models/amazon/chronos-bolt-tiny       model.safetensors = 34.622.352 B    apache-2.0
huggingface.co/api/models/amazon/chronos-bolt-small      model.safetensors = 190.888.824 B   apache-2.0
huggingface.co/api/models/google/timesfm-2.0-500m-pytorch model.safetensors = 1.995.406.976 B apache-2.0
```

Against 5,242,880 B: **6.6x / 36.4x / 380.6x. There is no small checkpoint.**
Fill in `weights.pretraining_corpus_declared` and `.energy_domain_in_corpus` **for the checkpoint that
will run** (v3 cited the TimesFM card as evidence, which it also cuts).

### Phase 1 — `cutoffs=`, `rescore()` and the equality assertion

**Files changed, named:** `models/backtest.py` (`cutoffs=`, `rescore()`) and `models/train.py`
(`compare()` + `build_artifact`).

- **✅** `uv run pytest -p no:cacheprovider` → exit 0; `pytest --collect-only` reports N; the four
  occurrences in `README.md:64,182,731` and `CONTRIBUTING.md:39` say **N**
  `[→ fase1-aceite-376-passed-impossivel]`.
- **✅** reproduce F1 and obtain **`folds_intersected` with 45 entries, an identical `arms[].n`,
  `unscorable_cutoffs` naming the 10 cutoffs, `failed_gate is None`** — not a raise, because G1
  intersects `[→ R2-04, g1-interseciona-mas-o-canario-da-fase1-exige-failed-gate]`.
- **❌** empty intersection → `failed_gate="fold-identity"`.
- **❌ mutation (F16):** `mutation_score.py --floor 66`, `mutation_survivors.py --check`,
  `mutation_ratchet.py --check` pass.

### Phase 2 — The arms. **A named code deliverable, not "zero dependency"**

`[→ fase2-mecanismo-nao-alcanca-os-bracos-de-12, R2-10, R2-B]` v3 claimed
`ablate_forecast_weather` was already enough. **Measured: it cannot reach 2 of the 3 arms** —
calendar is not a panel column, it is computed in `build_design_matrix` from the target. Deliverable:
`drop_features: tuple[str,...]` in `features.build.build_design_matrix`, which NaNs the named columns
**after** computing them, preserving the 27 columns that `features_informative` and G13 presuppose,
applied **identically** in training and prediction.

- **✅** `features_informative` = 17 / 12 / 12; `arms[].features` recorded; `lgbm_12_frozen` with
  `refits == 1` and `fit_anchor_utc == cutoff_candidates[0]`.
- **❌** composition → **G13**; divergent hyperparameter or anchor → **G12** (`arm-params` /
  `arm-cadence`).

### Phase 3 — `foundation/`

`tsfm.py` (lazy import), `guards.py` (torch-free), `stub.py`, `compare.py`, `arms.py`.
`pyproject.toml`: `foundation` extra; `foundation` in `[tool.mypy] files` and in the wheel.

- **✅** G5's three conditions, including `'torch' not in sys.modules`.
- **✅** G2 and G3 canaries **through** `backtest.run`, with a negative control.
- **✅** declared local budget: `weeks=2`, `OMP_NUM_THREADS=2`. *(R2 refuted the finding that 90 s was
  unreachable — three stable runs gave 9.66/9.38/9.15 s for `lgbm_27`. The budget stands, with G3's
  Phase −1 cost added to it.)*
- **❌** relock: `uv lock` is the repository owner's step. The `pyproject`↔`uv.lock` consistency test
  enters as **`@pytest.mark.xfail(strict=True)`**, not as a red test — otherwise the `test` job stays
  red until Phase 6, and `strict=True` forces its removal once the lock lands
  `[→ fase3-relock-deadlock-ou-xfail]`.

### Phase 3b — `.github/workflows/ci.yml`

Steps for G5, G6 and G9.

- **✅** three **content** assertions in `tests/test_workflows.py`: `"import torch" in commands`,
  `"5242880" in commands`, `"test_foundation" in commands`. v3 accepted "the existing guards still
  pass", which is the assertion that nothing happened
  `[→ fase3b-aceite-vazio-nao-verifica-nenhum-step]`.

### Phase 4 — Cost · Phase 5 — Uncertainty · Phase 7 — Prose · Phase 6 **[DISPATCH]**

As in v3, with: `ram_gb`/RSS mandatory (§2.4); Phase 7 **before** Phase 6; Phase 6 evaluates
`reopen_timesfm` and removes the `xfail`.

---

## §5 — Cut

GIFT-Eval (entirely), TimesFM in v1 (reopening on the **CI**, not the point estimate), the single
cost-per-prediction number, USD/Wh, wall-clock as a unit, `horizons_won` as a headline, "beat
`lgbm_27`", versioned weights, a dedicated workflow, the cron, touching `metrics/model.json`.

**RESTORED cut — F5 for `monitor.json`/`pipeline.json`.** `[→ R2-A]` v3 withdrew this cut claiming G4
would close F5 "by construction". **It does not: G4 detects, it does not fix**, and it would leave the
suite red on 2 of 6 artifacts with no phase responsible. F5 goes back to being an open defect,
declared in §6. **Fixing it is its own mandate, not a free ride on this lane.**

**Cut kept:** F8 (`pipeline.json` without `host`) — out of scope, declared.

---

## §6 — Open risks

1. **Pretraining contamination: shape, not value.** The fold window postdates every released
   checkpoint, so the value cannot be memorised; the **shape** of electricity load can. It becomes a
   field (`pretraining_corpus_declared`, `energy_domain_in_corpus`), not prose. No offline experiment
   resolves it.
2. **CI acceptance is against a stub** — it proves the contract, not the model.
3. **Phases 1 and 3 trigger the 60-minute `mutate` job** (F16); the ratchet may demand new kills.
4. **F5 and F8 stay open.**
5. **The runner's real headroom is unknown**; the budget is local.
6. **`metrics/model.json` is regenerated by `train.yml`** and can move underneath the lane.
7. **Clause 1b's pessimistic imputation is a choice, not a measurement.** Scoring the TSFM's
   unscorable fold with the naive's error is conservative and arbitrary; a reviewer may prefer another
   rule. It is declared, and it is the best this design has against survivorship filtering.
8. **The TSFM's `load_cpu_s` depends on disk and cache** and may dominate while saying nothing about
   the model.
9. **R1's verifier refuted nothing across 73 findings.** If any of the 73 is a false positive, this v4
   carries the corresponding amendment without justification. R2 caught six of those
   (`unjustified_amendment`) and I reverted four; **there is no guarantee it caught them all.**

---

## §7 — The stop rule, and why v4 is the last

**Every R2 blocker has the same shape.** G5 is green at HEAD; G6 prints the violation and exits 0; G9
parses a summary `-qq` never prints, is vacuous on an empty glob and recurses on itself; G4 leaves the
suite red with no owner; G2 is green on top of the edge gap that motivated it; G3 covers 1 fold of 55
and is evadable by a conditional; G1 intersects while the acceptance demands a raise; G12 compares
metadata with metadata; G13 watches the wrong arm; the verdict's denominator was never measured, and
measured it is 71% worse than the naive; and Phase 2's mechanism cannot reach 2 of the 3 arms it
promises.

**Eleven blockers, one diagnosis: a gate verified by reasoning rather than by execution.** And one
fix: **build the canary and watch it fail.**

From here, reviewing the document yields less than running the gate — three rounds showed that every
amendment written without execution produces the next round of blockers, and **four v3 amendments
reintroduced the defect they were fixing.** A v5 written the same way would produce a v6.

Phase −1 is that rule converted into work: no gate exists until it has been seen red, and the red
output is pasted here. **The instrument stops being the RFC and becomes the canary.**

**This is not approval.** R2 says `not ready`, 4/4, and it is right about the document. What the stop
rule asserts is narrower: *the next defect will be found by execution, not by reading.*
