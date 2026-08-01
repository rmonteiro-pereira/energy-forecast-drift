# energy-forecast-drift

> [!CAUTION]
> # ⚠️ EVERY NUMBER IN THIS REPOSITORY IS SYNTHETIC
>
> ### There is no EIA API key yet, so there is no real demand data. Nothing here is a benchmark, a result, or a claim about PJM.
>
> The demand series is a **seeded synthetic fixture** from
> [`models/fixtures.py`](models/fixtures.py). Every committed artifact carries
> **`"is_real": false`**, both PNGs are stamped `SYNTHETIC FIXTURE`, and the
> dashboard leads with a red banner that reads the flag out of the data.
>
> **If you are about to quote a number from this repo — an MAE, a MAPE, the
> LightGBM-vs-baseline delta, a PSI, the drift verdict — don't.** They exist to
> prove the pipeline executes end to end. They say nothing about electricity
> demand.
>
> **What *is* real is the engineering**, and that is what this repo is for:
> walk-forward backtesting with leakage blocked in four independent places, four
> drift types over hand-written PSI and KS, a retrain policy that returns a
> structured verdict, MLflow tracking and a gated registry promotion, and tests
> that prove the alarm fires on an injected shift *and* stays silent without one.
> None of that depends on which numbers go in.
>
> **The day the key arrives:** one backfill and one `pipeline.daily` run flips
> every artifact to `"is_real": true` — the banner turns green, the watermark
> disappears, and the same code starts producing numbers that mean something.
> Steps: **[docs/BLOCKED.md](docs/BLOCKED.md)**.

---

Hourly **electricity demand forecasting** for a US balancing authority (PJM),
built around a live data feed **so that model drift will be observed rather than
simulated — once the API key lands.** Today it is neither: the demand series is
the synthetic fixture described above, and the drift numbers describe that
fixture.

The point of the project is not the forecast. It is the loop around it, and the
loop is built: one command chains ingest → features → score → rolling-MAE
monitor → drift → artifacts, and `daily.yml` calls exactly that command. What it
does *not* yet do is run — the workflow is dormant until a key exists, precisely
so it cannot publish fixture numbers as though they were observations. When it is
activated, it will pull fresh demand and weather daily, re-score the frozen model
against the actuals that arrive, and commit the metrics back, so drift
accumulates in public week after week and can be pointed at.

## What is real, and what is not

| | Status | Notes |
|---|---|---|
| **The code** | ✅ real, complete, tested | 279 Python tests + 4 dashboard tests, no network. Every path below runs today, and [`docs/REPRODUCE.md`](docs/REPRODUCE.md) has the transcripts. The tests are themselves measured — see [mutation testing](docs/MUTATION-TESTING.md). |
| **Open-Meteo temperature** | ✅ **real data**, pulled live | No key needed. Genuinely fetched, genuinely joined. |
| **EIA hourly demand** | ❌ **absent** | The client is finished and not stubbed. It has never been given a key. |
| **The demand series used everywhere** | ❌ **seeded synthetic fixture** | `models/fixtures.py`, seed `20260728`. A plausible curve, not a measurement. |
| **Every number in `metrics/*.json`** | ❌ **fixture-derived** | MAE, MAPE, RMSE, bias, PSI, KS, the retrain verdict. All of it. `"is_real": false`. |
| **Both committed PNGs** | ❌ **fixture-derived** | Watermarked `SYNTHETIC FIXTURE — NOT REAL DATA` by `pipeline/plots.py`. |
| **The MLflow runs and registry** | ⚠️ real machinery, fixture inputs | Real tracking, real registry, real gated promotion — of a model fitted on the fixture. |

The `is_real` flag is not a comment. It is written into every artifact, tagged
onto every MLflow run, checked by `/forecast` before it answers, and read by the
dashboard banner at render time. Flipping it is a data event, not an edit.

## If you are reviewing this in five minutes

The claims worth checking, and where to check them:

| Claim | Where it is enforced | Where it is proven |
|---|---|---|
| No temporal leakage in the backtest | `models/backtest.py::_history_before` (`index < cutoff`, strictly) | `tests/test_backtest.py` — poisons every value after the last fold, asserts the metrics do not move |
| No temporal leakage in the *features* | `features/build.py` — every feature is a function of data strictly before its forecast **origin**, not its target | `tests/test_features_build.py` — poisons from the origin onward, asserts no feature column moves |
| PSI and KS are implemented, not imported | `drift/stats.py` — no scipy at runtime | `tests/test_drift_stats.py` — checks `D` against `scipy.stats.ks_2samp` to 1e-12, the p-value to 1e-3, plus a two-bin PSI worked out by hand |
| The drift alarm actually fires | `drift/trigger.py` — five named rules, structured verdict | `tests/test_drift_run.py` — injects a shift and asserts **retrain**; runs the identical path unshifted and asserts **not retrain** |
| Promotion to `@champion` is earned | `models/tracking.py` — alias moves only on beating the naive baseline | `tests/test_lgbm.py` — a losing model lands as `@challenger` |
| The monitor never scores itself in-sample | `pipeline/daily.py::_monitoring_booster` — needs the `train_data_end_utc` tag to prove otherwise | `tests/test_pipeline_daily.py`; the bug it fixes is written up in [`docs/writeup.md`](docs/writeup.md) §5.1 |
| A cron can never publish fixture numbers as real | `pipeline/daily.py` `--require-eia-key` → exit 2 before writing a byte | `tests/test_pipeline_daily.py`, plus a CI step that asserts exit 2 **and** that no file was written |
| The banner follows the data, not the copy | `dashboard/src/components.tsx::ProvenanceBanner` | `dashboard/src/components.test.tsx` — same props, flag flipped, banner changes state |
| No secret can reach a log | `ingest/http.py::redact` | `tests/test_clients.py::test_secrets_never_survive_redaction` |
| No artifact can claim to be real while it isn't | the `is_real` flag, written by every entrypoint | `tests/test_artifacts.py` — fails the build if any published artifact pairs `is_real: true` with synthetic provenance, or drops its warning |
| The tests would actually notice a defect | `.github/workflows/mutation.yml` — runs on every PR that can move the score, and fails below a floor of 66 | [`docs/MUTATION-TESTING.md`](docs/MUTATION-TESTING.md) — **66.9%**, measured on the CI runner over the detectors and the backtest split, with all 157 surviving mutants listed rather than summarised and the 4 remaining gaps named |
| The detector was checked against drift nobody designed | `scripts/drift_eval_real_weather.py` — real Open-Meteo observations, keyless | [`docs/DRIFT-EVALUATION.md`](docs/DRIFT-EVALUATION.md) — **it found a false positive in the shipped thresholds**: a fortnight of ordinary autumn cooling scores PSI 0.525 against an alert threshold of 0.20. Published because a monitor measured only against shifts its author injected has not been measured |

**Why the shape is what it is**, with the alternative rejected in each case and
the condition that would reverse it: **[docs/adr/](docs/adr/)** — seven records,
including [one that documents a bug that shipped](docs/adr/0005-monitor-refuses-in-sample-scoring.md).

Longer form, including three bugs this project actually had and what a real
drift episode is predicted to look like: **[docs/writeup.md](docs/writeup.md)**.
Real captured transcripts of every command above, including the ones that fail
on purpose: **[docs/REPRODUCE.md](docs/REPRODUCE.md)**. The pre-publication
secret and size scan: **[docs/PUBLICATION-SCAN.md](docs/PUBLICATION-SCAN.md)**.
An honest list of everything you might trip on here, including what is thin:
**[docs/PUBLICATION-READY.md](docs/PUBLICATION-READY.md)**.

**Status: M0 → M7 complete and committed** — ingestion, the seasonal-naive
baseline, a global LightGBM on the same walk-forward folds, MLflow tracking +
registry, the four-way drift suite with its retrain trigger, the single-command
daily pipeline behind `daily.yml`, a FastAPI `/forecast` from the registry
alias, the React dashboard, and the writeup. The only thing missing is data.

---

## Architecture

```mermaid
flowchart LR
    subgraph sources["Free data sources"]
        EIA["EIA Open Data v2<br/>hourly demand · PJM<br/><i>needs free key</i>"]
        OM["Open-Meteo<br/>hourly temperature<br/><i>no key</i>"]
    end

    subgraph pipeline["Local pipeline"]
        ING["ingest/<br/>incremental · idempotent"]
        LAKE[("data/<br/>partitioned parquet<br/><i>gitignored</i>")]
        FEAT["features/<br/>gapless panel + calendar<br/>+ origin-stamped design matrix"]
        MODEL["models/<br/>seasonal naive · LightGBM<br/>walk-forward backtest"]
        DRIFT["drift/<br/>own PSI + KS · Evidently<br/>feature · target · prediction<br/>· performance"]
    end

    subgraph mlops["MLflow · local, gitignored"]
        TRACK[("mlflow.db + mlruns/<br/>runs · params · metrics")]
        REG["registry<br/><b>@champion</b>"]
    end

    subgraph published["Committed artifacts"]
        METRICS["metrics/baseline.json<br/>metrics/model.json<br/>metrics/drift.json<br/>MAE + MAPE + drift verdict"]
    end

    EIA --> ING
    OM --> ING
    ING --> LAKE --> FEAT --> MODEL --> METRICS
    FEAT --> DRIFT --> METRICS
    MODEL --> DRIFT
    MODEL --> TRACK --> REG
    DRIFT -->|"retrain verdict"| REG
    REG --> SERVE["serving/<br/>FastAPI <b>/forecast</b><br/>loads @champion"]

    CRON["daily.yml<br/><i>inert until published</i>"] --> PIPE["pipeline.daily<br/>one entrypoint,<br/>six stages"]
    PIPE --> ING
    METRICS --> DASH["dashboard/<br/>Vite · React · ECharts<br/>banner driven by <b>is_real</b>"]
```

## Quickstart

```bash
uv sync --extra dev            # Python 3.11+, deps pinned in uv.lock

cp .env.example .env           # then paste your EIA key (see docs/BLOCKED.md)

uv run python -m ingest        # pull the delta from both sources
uv run python -m ingest        # re-run: reports +0 new rows — it is idempotent

uv run python -m models        # M1: walk-forward backtest -> metrics/baseline.json
uv run python -m models.train  # M2+M3: LightGBM vs baseline, MLflow -> metrics/model.json
uv run python -m drift.run --out metrics/drift.json   # M4: 4 drift types + retrain verdict

uv run python -m pipeline.daily  # M5: the whole loop -> metrics/*.json + PNGs
uv run python -m serving         # M5: FastAPI on :8000, /forecast from @champion

uv run pytest -v               # 279 tests, no network

cd dashboard && npm ci && npm test && npm run build   # M6: static dist/ over metrics/*.json
```

Every command above is captured verbatim, with its real output and exit code, in
[`docs/REPRODUCE.md`](docs/REPRODUCE.md).

`python -m models.train` is the train/eval entrypoint: it scores **both** models
on the same folds, logs the run to MLflow, registers the refit LightGBM and
writes `metrics/model.json` + `metrics/model_table.md`. It takes ~1 min on the
fixture (56 refits), plus a one-off ~40 s the first time it creates `mlflow.db`.

Useful flags:

| Command | Effect |
|---|---|
| `python -m ingest --source weather` | run one leg only (`eia`, `weather`, `all`) |
| `python -m ingest --full-refresh` | ignore the lake and re-pull the whole backfill |
| `python -m models --source real` | fail loudly instead of falling back to the fixture |
| `python -m models --source synthetic` | force the fixture (what CI smoke-tests) |
| `python -m models --weeks 12` | widen the backtest window |
| `python -m models.train --no-mlflow` | score only; skip tracking and the registry |
| `python -m models.train --train-stride-hours 24` | fewer training origins → faster, weaker |
| `python -m models.train --num-boost-round 600` | longer boosting |
| `python -m drift.run --simulate-shift 12000` | inject a +12 GW level shift to watch the alarm fire (artifact is stamped `simulated_shift`) |
| `python -m drift.run --fail-on-retrain` | exit 1 when the verdict says retrain — usable as a CI gate |
| `python -m drift.run --no-evidently` | skip the optional second opinion |
| `DRIFT_PSI_ALERT=0.15 python -m drift.run` | override any threshold from the environment |
| `uv run mlflow ui --backend-store-uri sqlite:///mlflow.db` | browse the runs and the registry |

## Baseline (M1)

**Model:** seasonal naive — `demand(T) = demand(T - 168h)`, i.e. the same hour
one week earlier. For an hourly load series this single lag captures the daily
shape *and* the weekday/weekend split, which makes it a genuinely hard trivial
benchmark, and a much fairer one than a 24 h naive.

**Protocol:** walk-forward, 56 daily folds over the last 8 weeks. At each fold
cutoff `T0` the model sees the series strictly before `T0` and forecasts
`T0+1 … T0+24`. Metrics are computed per horizon, then pooled.

<details>
<summary><b>⚠️ SYNTHETIC FIXTURE OUTPUT — not a result, not a benchmark. Click only if you accept that.</b></summary>

**Read this before the table.** Every cell below is computed from
`models/fixtures.py` — a seeded curve, not the EIA. The table demonstrates that
the backtest runs, that it is scored per horizon, and that the artifact is well
formed. It is **not** a measurement of anything, and the figures are deliberately
left unbolded so that nothing here reads as a headline.

| Horizon (h) | MAE (MWh) | MAPE (%) | RMSE (MWh) | Bias (MWh) | n |
|---:|---:|---:|---:|---:|---:|
| 1 | 2,621 | 3.36 | 3,155 | -779 | 56 |
| 6 | 2,491 | 3.27 | 3,244 | -485 | 56 |
| 12 | 2,681 | 2.53 | 3,322 | -500 | 56 |
| 18 | 2,906 | 2.46 | 3,397 | -520 | 56 |
| 24 | 2,844 | 3.46 | 3,623 | -178 | 56 |
| overall | 2,559 | 2.77 | 3,173 | -487 | 1,344 |

*(fixture-derived — `metrics/baseline.json` carries `"is_real": false`)*

Full per-horizon table: [`metrics/baseline_table.md`](metrics/baseline_table.md).

</details>

**The role this baseline plays is structural, not numeric.** Whatever its MAE
turns out to be on real data, it is the number every later model must beat — on
the same folds, the same horizons, the same protocol. That comparison is the
point; the current value of it is not.

## M2 — LightGBM, on the same folds

**Model:** one **global, direct** LightGBM. A single booster covers all 24
horizons with `horizon_h` as an input feature, rather than 24 separate models or
a recursive one-step model fed its own output. Direct multi-horizon cannot
compound its own error the way recursion does, and a global fit sees 24× more
rows than a per-horizon fit — which matters when the history is months, not
years.

**Features (20)** — calendar (hour / day-of-week / month / weekend / US federal
holiday), demand lags at 24 h, 48 h, 168 h and 336 h, the same-hour-of-week mean
over four weeks, rolling mean/std/min/max of the last 24 h and 168 h, and the
Open-Meteo temperature in the same two shapes.

**Refit cadence:** the model is **retrained at every one of the 56 fold
cutoffs**, on exactly the rows whose target hour had already happened at that
instant. Fold 56's model never sees anything fold 1's model could not have seen.

<details>
<summary><b>⚠️ SYNTHETIC FIXTURE OUTPUT — not a result, not a benchmark. Click only if you accept that.</b></summary>

**The delta below is the most quotable-looking number in this repository and the
most misleading.** It is fixture against fixture. A synthetic curve is easier to
fit than real load, so a win here is close to guaranteed and means only that the
two models were scored on identical folds and the comparison plumbing works. It
is not evidence that LightGBM beats a seasonal naive on PJM. Unbolded on purpose.

| | MAE (MWh) | MAPE (%) |
|---|---:|---:|
| seasonal naive | 2,559 | 2.77 |
| LightGBM | 2,181 | 2.38 |
| delta | −378 (−14.8%) | −0.39 pp |

*(fixture-derived — `metrics/model.json` carries `"is_real": false`)*

LightGBM leads on 23 of the 24 horizons *on this fixture*. Full per-horizon
comparison: [`metrics/model_table.md`](metrics/model_table.md); machine-readable
[`metrics/model.json`](metrics/model.json).

Top gain-based importances: `demand_lag_168h` (39%),
`demand_same_hour_of_week_mean_4w` (20%), `demand_lag_48h` (7%),
`demand_lag_336h` (7%), `demand_lag_24h` (6%), `temp_lag_168h` (5%) — i.e. the
booster rediscovers the weekly seasonality the baseline hardcodes, and then adds
temperature and the recent level on top. That is the shape you would want to
see; on the fixture it is also the shape that was *put there*, so it confirms
the plumbing rather than the physics.

</details>

## M3 — MLflow tracking + registry

Every `models.train` run logs both models' per-horizon curves, the LightGBM
hyper-parameters and the panel provenance to **MLflow on a sqlite backend**,
then refits LightGBM on the whole panel and pushes it to the **model registry**.

sqlite rather than the default `./mlruns` file store for one reason: the file
store has **no registry**. The registry is the point of M3 — serving (M6) asks
for `models:/energy-demand-forecaster@champion` instead of a hardcoded path, so
promoting a model is a registry operation, not a deploy.

**Promotion is gated, not automatic.** The alias `@champion` is only moved onto
the new version when it actually beat the seasonal naive on the shared folds;
otherwise it lands as `@challenger` and the artifact records
`"beats_baseline": false`. A model that loses to a one-line baseline does not
get to be champion.

```bash
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db   # runs, metrics, registry
```

`mlflow.db` and `mlruns/` are **gitignored and never committed** — they are
local run state. `metrics/*.json` stays the only published surface, and CI fails
the build if either ever gets tracked.

## M4 — the drift suite

```bash
uv run python -m drift.run --out metrics/drift.json
```

**Four drift types, because they are four different failure modes.** A monitor
that implements one of them is the usual mistake:

| | what moved | needs labels? | what it tells you |
|---|---|---|---|
| **feature** | the model inputs | no | leading indicator — the model may still be fine, if it does not lean on the column that moved |
| **target** | the observed demand | yes | a load regime the model was never fitted on |
| **prediction** | the model output | **no** | the *earliest* signal available in production, because actuals arrive late |
| **performance** | rolling MAE / MAPE | yes | the only signal that proves harm — and the slowest |

**PSI and KS are written out, not imported.** Both are three-line formulas
wrapped in a lot of edge cases, and the edge cases are where drift detectors
quietly stop working: a bin with zero reference mass makes PSI infinite, a
constant column collapses the quantile edges, a 30-row window makes everything
significant. `drift/stats.py` names and handles each one — reference-defined
bin edges open at ±∞ so out-of-range values are not silently dropped, shares
floored rather than skipped (a bin that lost all its mass is the event PSI
exists to catch), category binning for low-cardinality columns. The tests check
`D` against `scipy.stats.ks_2samp` to 1e-12 and the p-value to 1e-3, plus a
two-bin PSI worked out on paper.

**Evidently runs next to it, not instead of it.** It is an independent second
opinion with its own tests and thresholds; a disagreement would mean a bug in
our number. It is recorded in the artifact and **not** wired into the trigger,
and it is an optional dependency — a missing Evidently produces
`"status": "unavailable"`, never a failed pipeline.

**Calendar features are reported but never vote.** A 28-day reference against a
14-day current window necessarily spans different months, so `month` scores
PSI ≈ 7 on every healthy run and `is_holiday` swings on the luck of the
calendar. Letting deterministic functions of the timestamp drive the alarm
would mean firing every single day. They stay in the artifact — useful for
sanity-checking the window geometry — and are excluded from the verdict.

**Both scored windows are out of sample.** The history is cut three ways —
train / reference / current — and the booster is fitted on the train slice
*only*. Scoring the reference window with a model fitted on it would make the
reference errors flatteringly small and every later window look degraded
forever.

**The trigger is a policy, not a threshold.** Retraining on every PSI excursion
means retraining constantly — and often on a window too short to have learned
the new regime, producing a champion worse than the one it replaced. So:

| rule | condition | verdict |
|---|---|---|
| **R1** | performance alerts | **retrain** — measured harm, nothing else needed |
| **R2** | a distribution signal alerts *and* performance warns | **retrain** — cause plus visible effect |
| **R3** | two or more distribution signals alert | **retrain** — a regime change, act before the errors confirm it |
| **R4** | anything else non-`ok` | **watch** — charted, not acted on |
| **R5** | all four `ok` | **healthy** |

The verdict is a structure, never a bare bool: `should_retrain`, the rule that
fired, every reason as a metric/threshold pair, and a per-signal map. A pipeline
branches on one field; a human audits the rest.

**The alarm is tested in both directions.** `drift/simulate.py` injects a shift
of a stated size, and the tests assert the alarm fires on it — then run the
identical code path on the untouched fixture and assert it does not. A detector
that never fires is useless; one that always fires is worse, because it trains
people to ignore it.

<details>
<summary><b>⚠️ SYNTHETIC FIXTURE OUTPUT — not a result, not a benchmark. Click only if you accept that.</b></summary>

**A drift verdict computed on a fixture is a demonstration of the rule, not a
finding.** The windows below are two slices of a seeded curve; that they differ
tells you about the curve, not about the grid.

On the fixture the current verdict is WATCH: feature drift alerts (the
fixture carries a real annual cycle, so mid-June-vs-mid-July temperature and
rolling-level features genuinely move), while target, prediction and
performance stay quiet. That is exactly the case R4 exists for — a leading
indicator with no measured harm behind it.

Injecting a +12,000 MW level shift over the current window flips all four
signals to `alert` and the verdict to RETRAIN under R1, with the reference MAE
roughly tripling. Reproduce with `--simulate-shift 12000`; the artifact is
stamped `simulated_shift` so a demo can never be mistaken for an observation.
This is the one number in this section that is *supposed* to be artificial — it
is an injected shift of a stated size, and the alarm responding to it is the
assertion under test.

Full report: [`metrics/drift_summary.md`](metrics/drift_summary.md); machine
readable [`metrics/drift.json`](metrics/drift.json).

One honest caveat visible in that artifact: PSI is scale-free *relative to the
reference spread*, so heavily smoothed features (`demand_roll_mean_168h`) show
enormous PSI for level moves that are small in MW. Narrow reference bins make
small absolute moves look catastrophic. That is a property of PSI, not a bug —
it is why the section verdict uses the share of drifted columns rather than the
maximum, and why a distribution alert alone does not retrain.

</details>

## M5 — the daily pipeline and serving

### One entrypoint, six stages

```bash
uv run python -m pipeline.daily          # ingest → features → score → monitor → drift → artifacts
```

```
ingest → features → score → rolling-MAE monitor → drift → metrics/*.json + 2 PNGs
```

**Everything the cron does lives in Python, not in YAML.** `daily.yml` runs
exactly one command. A pipeline spread across ten workflow steps can only be
debugged by pushing a commit and watching a red tick; this one runs on a laptop
and has tests. Each stage records its status, duration and a detail block into
`metrics/pipeline.json`, which is written **even when the run fails** — a failed
cron leaves an artifact explaining itself instead of only a red tick.

**Ingestion is the only stage allowed to degrade.** A source being down must not
stop the model being re-scored against the history already in the lake.
Everything after it is fatal, because a scoring step that silently half-worked
is worse than a failed run.

**`--require-eia-key` makes the worst failure mode impossible.** A cron that
quietly publishes fixture numbers as if they were data is the single worst thing
this repo could do, so the workflow passes that flag: no key means exit 2 with
printed instructions, before a single byte is written. Locally, without the
flag, the same entrypoint degrades to the fixture — which is what keeps the
whole thing runnable and testable today.

**The monitor refuses to score itself.** This one is subtle and it is the bug
this milestone actually had. The registry champion is refit on *all* available
history, so by the time it is promoted it has already seen the reference and
current windows; scoring them with it gives in-sample errors. On the fixture the
gap was stark — roughly 1,015 MWh in-sample against roughly 2,657 out of sample
for the same model — and it was that ratio, not a failing test, that exposed the
bug. (Both figures are fixture-derived and quoted here only as the symptom.)
Every future window would then look catastrophic against a reference that was
never real. So training runs now tag the model with `train_data_end_utc`, and the
monitor uses the champion **only** when that tag proves its data stopped before
the reference window opens. Otherwise it fits its own booster on the train slice
and records why, in the artifact. A missing tag counts as ineligible: unknown is
not safe.

Because of that, `metrics/*.json` distinguishes two models and never conflates
them: `served_model` (what `/forecast` returns) and `monitoring_model` (what
scored the windows the alarm reads).

| Artifact | What it holds |
|---|---|
| `metrics/forecast.json` | day-ahead forecast vs the actual that arrived, plus the live forward forecast whose actuals do not exist yet |
| `metrics/monitor.json` | rolling MAE/MAPE per day, the reference level and the retrain line |
| `metrics/drift.json` | the four drift sections + the retrain verdict |
| `metrics/pipeline.json` | the run record: stage statuses, durations, artifacts, provenance |
| `metrics/forecast_vs_actual.png`, `metrics/rolling_mae.png` | the same two stories as images — watermarked `SYNTHETIC FIXTURE` while `is_real` is false |

### Serving: `/forecast` from the registry alias

```bash
uv run python -m serving                                  # http://127.0.0.1:8000/docs
curl 'http://127.0.0.1:8000/forecast?max_horizon=6'
```

```json
{
  "origin_utc": "2026-07-28T01:00:00+00:00",
  "is_real": false,
  "warning": "These numbers come from a SEEDED SYNTHETIC FIXTURE ...",
  "model": {
    "uri": "models:/energy-demand-forecaster@champion",
    "version": "2",
    "trained_on_real_data": false
  },
  "forecast": [{ "horizon_h": 1, "target_utc": "...", "forecast_mwh": 78091.6, "actual_mwh": null }]
}
```

Note the second and third fields. **The response carries its own provenance**, so
a consumer cannot receive a forecast without also receiving the fact that it came
from a fixture. `78091.6` is a fixture number like every other one here.

**No path is hardcoded.** The booster comes from
`models:/energy-demand-forecaster@champion`, so promoting a challenger is a
registry operation and nothing is redeployed. `/model` reports which version
actually answered.

**Features are not re-implemented for serving.** The request goes through the
same `features.build.build_design_matrix` that produced the training matrix, so
a feature cannot be computed one way for fitting and another way for serving —
the classic training/serving skew.

**Origins outside the information set are refused, not guessed.**
`build_design_matrix` does not complain about an origin with no history behind
it; it emits NaN features, which LightGBM consumes happily and turns into a
confident-looking number. `/forecast` bounds the origin to
`[panel_start + 672h, last_observed + 1h]` and returns 422 with the valid range.

**Every response carries its provenance**, and `is_real` is true only when the
panel *and* the model are real. A champion trained on the fixture keeps the
response synthetic even after real demand lands in the lake — until it is
retrained, the forecast is still a fixture artifact.

## M6 — the dashboard

```bash
cd dashboard && npm ci && npm run build && npx serve dist
```

Vite + React + ECharts, static output, **no deploy step in this repo**. The build
copies `metrics/*.json` into `dist/data/`, so the result is a directory that can
be served from anywhere — and because the data is *fetched* rather than inlined
into the bundle, pointing it at a fresher `metrics/` needs no rebuild.

**The banner is driven by the flag, not by copy — and that is tested.** While
`"is_real"` is false, the page leads with a red banner saying plainly that every
number came from a seeded synthetic fixture, and quoting the artifact's own
`warning` field rather than a string in the frontend. There is no prop, no build
flag and no environment variable that overrides it: `ProvenanceBanner` branches
on the artifact and nothing else.

```bash
cd dashboard && npm test     # 4 tests, all on the banner
```

`dashboard/src/components.test.tsx` renders the component twice with **identical
props except `is_real`** and asserts the two states differ in substance, not
wording — `role="alert"` present or absent, a different heading, the word
"benchmark" present or absent. A future refactor that "simplifies" the banner
into a constant fails those tests. `dashboard/README.md` also has the manual
version: flip the flag on a *copy* of `dist/data` and watch the same code render
a green "Live data" banner over the same numbers.

Four charts, and the decisions behind them:

| Chart | Reads | Why it looks like that |
|---|---|---|
| Forecast vs actual | `forecast.json` | The live forecast keeps the *forecast* hue and is separated by dash pattern and a shaded band — it is the same entity as the scored forecast, it just has no actual yet. A third colour would claim otherwise. |
| Drift over time | `drift.json` → `timeline` | Feature PSI runs ~100× the target and prediction PSI. **Not** a second y-axis — that would invent an alignment between two scales. A log axis keeps one scale, with the warn/alert thresholds drawn so the eye reads distance from the line. |
| Rolling forecast error | `monitor.json` | Daily MAE as thin bars, rolling mean as a line, reference level and retrain line as dashed rules, current window shaded. One axis, two marks. |
| Feature drift right now | `drift.json` | **Dots, not bars.** PSI spans three orders of magnitude here, so the axis has to be logarithmic — and a bar's length on a log axis is measured from the axis minimum, which would make a feature at PSI 0.02 look two thirds as drifted as one at 6.7. A dot encodes value by position, which survives any scale. |

Every chart has a table-view toggle, because a tooltip must never be the only path
to a value. The palette lives once in `styles.css` as CSS custom properties and is
read back at render time — ECharts needs literal hex, and a second copy in
TypeScript would drift from the stylesheet, most visibly in dark mode. Three
categorical slots plus a reserved status palette, validated in both modes against
both surfaces (worst all-pairs CVD ΔE 9.2 light / 9.4 dark).

## Design decisions worth defending

**Ingestion is incremental *and* idempotent.** The store de-duplicates on
`(entity, timestamp)` keeping the newest row, so re-running never duplicates an
hour — and because the EIA revises recent values, every run deliberately
re-pulls a 3-day tail so revisions *overwrite* stale numbers instead of being
ignored forever. Partition files are written to a temp path and moved into
place, so an interrupted run cannot leave a corrupt parquet.

**No temporal leakage, enforced in four independent places.**
`backtest._history_before` slices with `index < cutoff` (strictly — the hour
stamped `T0` is not complete at `T0`); `baseline.predict` re-asserts that neither
the history it received nor the seasonal lag it is about to read touches the
cutoff; `features.build` pins every feature to its forecast origin (below); and
`lgbm.training_slice` admits a training row only once its *label hour* is over,
raising if the slice ever reaches the cutoff. Tests poison every value after the
last fold and assert the metrics do not move — for both models — spy on the
model to assert it never saw a timestamp `>= cutoff`, and spy on the training
slice to assert the same of every label.

**Features are stamped with an origin, not a target.** A row of the design
matrix is a *(origin `O`, horizon `h`)* pair, and every feature on it must be a
function of data strictly before `O` — not before the target `T = O + h`. That
distinction is where feature engineering usually leaks: a 24 h lag looks
innocent, but for a 24 h-ahead forecast `T - 24h` **is** the origin, an hour
that has not finished yet. So lags are computed against the target and then
masked out when they would reach the origin; LightGBM eats the resulting NaN
natively, and `horizon_h` is a feature, so the model learns that distant
horizons simply have less to go on. Tests poison every value from the origin
onwards and assert that not one feature column moves.

**Only past weather is used.** Open-Meteo publishes a forecast, and the lake
already tags it `is_observed=False`, so a production forecaster could legitimately
feed tomorrow's forecast temperature in. This one does not — that would make the
"features use only data ≤ origin" claim depend on a second, unmodelled forecast,
and the point of this repo is that the rigour claims are *testable*. Wiring the
forecast leg in is a later, explicit step, not a silent one.

**Promotion is earned.** The registry alias `@champion` moves only when the
challenger beat the seasonal naive on identical folds; otherwise it is filed as
`@challenger`. Auto-promoting whatever trained last is how a worse model reaches
production quietly.

**The panel is gapless.** Missing hours become explicit NaNs rather than
shifting the index, so "168 rows ago" and "168 hours ago" stay the same thing.
A fold with a gap in its actuals is *skipped and reported*, never silently
scored — so every horizon is evaluated on an identical fold set and the columns
are comparable.

**Secrets cannot leak.** `.env` is gitignored, URLs are redacted before logging
and secret-looking query params are masked; a test asserts a key cannot survive
either path. A 401/403 is never retried — a bad key only burns quota.

**Rate limits are respected structurally.** All HTTP goes through one helper:
max 3 attempts, exponential backoff (2s/4s/8s), `Retry-After` honoured and
capped, sleeps between pages, and only transient statuses retried. No client
can bypass it.

**The lake is not committed.** `data/` is gitignored; `metrics/` holds only
small JSON that the future cron will refresh — it is the published surface the
M6 dashboard will read.

## Layout

```
ingest/     EIA v2 + Open-Meteo clients, polite HTTP, partitioned parquet store
features/   panel.py  gapless hourly panel, weather join, calendar
            build.py  origin-stamped design matrix (lags, rolling, holiday)
models/     baseline.py seasonal naive · lgbm.py global LightGBM
            backtest.py walk-forward protocol (shared by both models)
            tracking.py MLflow sqlite + registry · train.py the M2/M3 entrypoint
drift/      stats.py  own PSI + two-sample KS (no scipy at runtime)
            windows.py train/reference/current split, both scored out of sample
            detectors.py the four drift types · trigger.py the retrain policy
            config.py every threshold · evidently_report.py second opinion
            simulate.py injected shifts (tests + demo) · run.py the M4 entrypoint
pipeline/   daily.py  the six-stage entrypoint daily.yml calls
            plots.py  the two committed PNGs (watermarked when synthetic)
serving/    app.py    FastAPI /forecast /model /health from the registry alias
metrics/    committed artifacts: baseline.json, model.json, drift.json,
            forecast.json, monitor.json, pipeline.json + tables + 2 PNGs
dashboard/  Vite + React + ECharts over metrics/*.json — no deploy step here
            components.test.tsx  the banner tests (vitest)
tests/      279 Python tests: idempotency, leakage (backtest *and* features),
            retries, secret redaction, registry wiring, PSI/KS vs scipy, drift
            injection, threshold boundaries, the daily chain, the HTTP surface,
            both workflow YAMLs, and the artifacts' own honesty contract
docs/       adr/      7 decision records, each with the rejected alternative
            writeup.md (real vs fixture, three bugs, what a real episode looks
            like) · REPRODUCE.md (real transcripts of every command)
            MUTATION-TESTING.md (66.9% measured in CI, every survivor judged)
            PUBLICATION-SCAN.md (pre-publication secret + size scan)
            PUBLICATION-READY.md (what a reviewer will trip on, and what is thin)
            spec.md (the original brief — in Portuguese) · BLOCKED.md (the key)
.github/    ci.yml (active on publish) · daily.yml (inert until published)
mlruns/     MLflow artifacts — gitignored, never committed (nor is mlflow.db)
reports/    Evidently HTML (~5MB of inlined plotly) — gitignored
```

## What is left

Exactly one thing: **real data.** No code is waiting to be written.

| | |
|---|---|
| **gated on the EIA key** | backfill two years of hourly PJM demand, re-run `models.train` and `pipeline.daily` against it, and every artifact flips to `"is_real": true` — the banner turns green, the watermark disappears, and the figures in this README stop being placeholders and start being measurements |
| **then** | uncomment the `schedule:` block in `daily.yml` and let drift accumulate in public, day after day |
| **then** | one real drift episode, captured end to end, appended to the writeup — the thing the whole repo is built to catch |

The steps to unblock it are in [`docs/BLOCKED.md`](docs/BLOCKED.md); what will
change, and what a real episode is predicted to look like, is in
[`docs/writeup.md`](docs/writeup.md). Full brief:
[`docs/spec.md`](docs/spec.md) *(in Portuguese — it is the original brief, left
as written)*. Pre-publication scan:
[`docs/PUBLICATION-SCAN.md`](docs/PUBLICATION-SCAN.md); readiness assessment:
[`docs/PUBLICATION-READY.md`](docs/PUBLICATION-READY.md).

## Cost

R$0. EIA and Open-Meteo are free, GitHub Actions is free on a public repo, and
the dashboard is a static `dist/`. No server stays on.

## Contributing, security, license

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — setup, the four checks to run before a
  PR, and the house rules that exist for a reason.
- **[SECURITY.md](SECURITY.md)** — how to report something privately, and exactly
  how the one secret in this project is handled.
- **[MIT](LICENSE)** — the code is yours to use. The numbers are not results, so
  there is nothing there to cite.
