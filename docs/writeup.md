# energy-forecast-drift — what this is, what is real, and what is not

*Last updated: 2026-07-29. Milestones M0–M6 complete; the EIA API key is still
pending, so every metric in the repo is fixture-derived.*

---

## 1. The short version

This repo forecasts hourly electricity demand for a US balancing authority (PJM)
and monitors the forecast for drift. The forecast is not the interesting part —
a seasonal-naive baseline gets most of the way there, and everybody knows it. The
interesting part is the loop around it: a free daily cron pulls fresh demand and
weather, re-scores a frozen model against the actuals that arrived, computes four
kinds of drift, decides whether to retrain, and commits the numbers back to the
repo. Drift accumulates in public, week after week, and can be pointed at.

**None of the numbers in this repo are results yet.** The EIA API key has not been
registered, so the demand series is a seeded synthetic fixture. Every artifact
carries `"is_real": false`, the dashboard leads with a red banner, and the PNGs
are watermarked. This document is explicit about which parts are real code
running on real data, which parts are real code running on a fixture, and what
will change on the day the key lands.

---

## 2. What is real, right now

| Component | Status | Notes |
|---|---|---|
| **Open-Meteo ingestion** | ✅ **real data, running today** | No key needed. 744 hourly rows of Philadelphia temperature in the lake at the time of writing; the archive/forecast stitch and the revision re-pull both work against the live API. |
| **EIA client** | ✅ **finished, not stubbed** | Pagination, the 5000-row cap, respondent discovery against the facet endpoint, retries, secret redaction — all implemented and tested against `httpx.MockTransport`. It has never made a real request, because there is no key. |
| **Incremental + idempotent store** | ✅ real | Partitioned parquet, de-duplicated on `(entity, timestamp)` keeping the newest row, atomic temp-then-move writes. Re-running ingestion reports `+0 new rows`. |
| **Feature builder** | ✅ real code | Origin-stamped design matrix; the no-leakage property is asserted by tests that poison the future and check no feature column moves. |
| **Walk-forward backtest** | ✅ real code | 56 daily folds × 24 horizons, identical for every model. |
| **LightGBM + MLflow registry** | ✅ real code | Refit at every fold cutoff; sqlite backend; `@champion` alias moves only on a genuine win. |
| **Drift suite** | ✅ real code | Own PSI and KS (checked against `scipy.stats.ks_2samp` to 1e-12 on the statistic), four drift types, structured retrain verdict, Evidently as a second opinion. |
| **Daily pipeline + serving** | ✅ real code | `python -m pipeline.daily` runs end to end locally; `/forecast` serves the registry champion over HTTP. |
| **Dashboard** | ✅ real code | Vite + React + ECharts reading `metrics/*.json`. |
| **Demand series** | ❌ **synthetic fixture** | `models/fixtures.py`, seed 20260728, 200 days ending 2026-07-28. |
| **Every metric** | ❌ **fixture-derived** | `metrics/baseline.json`, `model.json`, `drift.json`, `monitor.json`, `forecast.json` — all `"is_real": false`. |

The dividing line is simple: **the code is real, the demand data is not.** Nothing
is mocked, stubbed or faked in the pipeline; the only substitution is the input
series, and it is substituted loudly.

---

## 3. Why a fixture at all, instead of waiting

Two bad options and one adequate one.

*Wait for the key* and the repo is a directory of untested code with a README
promising it works. *Fake the numbers* and it is worse than nothing.

*Run the whole pipeline on a deterministic, obviously-synthetic series* keeps
every line of code executable and testable today, and makes the substitution
impossible to miss: a fixed seed, a fixed anchor date (so committed artifacts do
not churn on every run), `"is_real": false` on every artifact, a red banner on
the dashboard, a watermark on every PNG, and a `--require-eia-key` flag that makes
the cron refuse to publish rather than silently ship fixture numbers as data.

The fixture is a plausible-looking load curve — daily and weekly cycles, an annual
cycle, an evening peak, a V-shaped temperature response, Gaussian noise. It is
shaped like demand so the plots look sane and the code paths are exercised. It is
**not** calibrated to PJM and **no** number derived from it means anything about
the grid.

---

## 4. What the pipeline actually does

```
ingest ──► features ──► score ──► rolling-MAE monitor ──► drift ──► metrics/ + PNGs
   │           │           │                │               │
Open-Meteo   gapless    frozen         daily MAE       PSI · KS · 4 types
  + EIA      panel +    booster,       vs reference    ──► retrain verdict
             design     out of                              │
             matrix     sample                       registry @champion
```

One command — `python -m pipeline.daily` — and `daily.yml` calls exactly that
command and nothing else. A pipeline spread across ten YAML steps can only be
debugged by pushing a commit and watching a red tick; this one runs on a laptop
and has tests.

### The four drift types

They are four different failure modes, and a monitor that implements one of them
is the usual mistake:

- **feature drift** — the inputs moved. Leading indicator. The model may be fine,
  because it may not lean on the column that moved.
- **target drift** — the observed demand moved. A load regime the model was never
  fitted on.
- **prediction drift** — the model's *output* distribution moved. The only signal
  computable with **no labels at all**, which matters because the actual demand
  for the last hour arrives with a lag. It is the earliest signal available.
- **performance drift** — the rolling error got worse. The only signal that proves
  harm; also the slowest, because it waits for the actuals.

### The retrain policy

Distribution drift is a leading indicator, not proof of harm. Winter arrives every
year: temperature PSI goes through the roof and a model with a temperature feature
handles it. Retraining on every PSI excursion means retraining constantly, often
on a window too short to have learned the new regime — producing a champion worse
than the one it replaced.

| Rule | Condition | Verdict |
|---|---|---|
| R1 | performance alerts | **retrain** — measured harm, nothing else needed |
| R2 | a distribution signal alerts *and* performance warns | **retrain** — cause plus visible effect |
| R3 | two or more distribution signals alert | **retrain** — a regime the model never saw |
| R4 | anything else non-`ok` | **watch** — charted, not acted on |
| R5 | all four `ok` | **healthy** |

The verdict is a structure, never a bare bool: `should_retrain`, the rule that
fired, every reason as a metric/threshold pair, and a per-signal map.

---

## 5. Three things I got wrong, and what they cost

These are in the writeup because they are the parts worth reading.

### 5.1 The monitor was scoring itself

The first version of the daily pipeline loaded the registry champion and used it
to score both monitoring windows. That is wrong, and it took a suspicious number
to notice: the reference MAE came out at **1,015 MWh** where the same model scored
**2,657 MWh** out of sample.

The champion is refit on *all* available history, so by the time it is promoted it
has already learned the reference and the current window. Scoring them with it
gives in-sample errors, which makes the reference level artificially low — and
then every future window looks catastrophically degraded against a baseline that
was never real. A drift monitor built that way fires forever and gets muted.

The fix: training runs now tag the model with `train_data_end_utc`, and the
monitor uses the champion **only** when that tag proves its training data stopped
before the reference window opens. Otherwise it fits its own booster on the train
slice and records the reason in the artifact. A missing tag counts as ineligible —
unknown is not safe. The artifacts now distinguish `served_model` (what
`/forecast` returns) from `monitoring_model` (what scored the windows the alarm
reads), because conflating them is exactly how the bug happened.

On the current fixture the champion *is* ineligible, and `metrics/drift.json`
says so in plain text.

### 5.2 Calendar features made the alarm fire every day

The first drift run reported `month` at PSI 7.5 and flagged 10 of 20 features.
That is not drift; it is arithmetic. A 28-day reference window and a 14-day
current window necessarily span different months, so `month` scores an enormous
PSI on *every* healthy run, and `is_holiday` swings on whether either window
happened to contain a holiday.

Deterministic functions of the timestamp are now reported but **excluded from the
verdict**. They stay in the artifact — they are a useful sanity check on the
window geometry — and they never vote. Letting them vote would mean the
feature-drift signal fires every single day and therefore means nothing.

### 5.3 PSI on smoothed features is hypersensitive, and that is not a bug

On the unshifted fixture, `demand_roll_mean_168h` scores PSI 4.1 while
`demand_lag_168h` scores 0.03 — on the same underlying series. The reason: PSI is
scale-free *relative to the reference spread*, and a 168-hour rolling mean has a
very narrow one. Quantile bins built on a smoothed series are thin, so a level
move that is small in MW walks across many of them.

This is a property of PSI, not a defect in the implementation, and it is why:

- the section verdict uses the **share** of drifted columns rather than the
  maximum;
- a distribution alert alone never triggers a retrain;
- the dashboard plots feature PSI on a **log** axis, as dots rather than bars —
  a bar's length on a log axis is measured from the axis minimum, which would make
  a feature at PSI 0.02 look two thirds as drifted as one at 6.7.

---

## 6. Reading the current (synthetic) report

The committed `metrics/drift.json` says **WATCH** under rule R4:

| Signal | Severity | What it says |
|---|---|---|
| feature | 🔴 alert | 8 of 14 eligible features above PSI 0.2; worst is `demand_roll_min_24h` at 6.66 |
| target | 🟢 ok | demand PSI 0.022, mean moved −133 MWh |
| prediction | 🟢 ok | forecast PSI 0.027, mean moved −244 MWh |
| performance | 🟢 ok | MAE 2,324 → 2,534 MWh (+9.0%), MAPE +0.27 pp |

The feature alert is genuine, not noise: the fixture carries a real annual cycle,
so mid-June-vs-mid-July temperature and rolling-level features do move. That is
exactly the situation R4 exists for — a leading indicator with no measured harm
behind it, recorded and charted, not acted on.

Injecting a +12,000 MW level shift over the current window
(`python -m drift.run --simulate-shift 12000`) flips all four signals to `alert`
and the verdict to **RETRAIN** under R1, with the MAE roughly tripling. The
artifact from that run is stamped `simulated_shift` so a demo can never be
mistaken for an observation. CI runs both directions on every push: the alarm must
fire on the injected shift, and must stay silent without it.

**Again: none of these numbers describe PJM.** They describe a seeded curve.

---

## 7. What a real drift episode will look like

Once the key lands and the cron has been running for a few weeks, the failure
modes below are the ones I expect to actually show up. Writing them down now,
before any of them has happened, is the point — it makes the prediction checkable.

**A heatwave (the textbook case).** Temperature features move first: `temp_last_1h`
and `temp_roll_mean_24h` cross PSI 0.2 within a day or two. Demand follows — target
drift alerts a day later as the load distribution shifts right. Prediction drift
alerts at the same time, because the model *does* have a temperature response and
will follow the inputs part of the way. Performance is the question: if the model's
thermal response is well specified in that range, MAE barely moves and the verdict
stays **watch** under R4 — the right answer, and the one a naive PSI-threshold
monitor would get wrong by retraining. If the heatwave is outside anything in the
training history, MAE degrades and R2 fires within a day of the actuals arriving.

**An EIA revision.** The EIA restates recent hours; ingestion deliberately re-pulls
a 3-day tail so revisions overwrite rather than being ignored forever. A large
restatement moves the *target* distribution without moving the features, which is a
distinctive signature: target alerts, feature stays quiet, and performance degrades
retroactively as previously-scored hours change value. That combination should be
read as a data-quality event, not a model event, and it is the case where the
current policy is weakest — R2 would fire and retrain a model that was never wrong.
The fix, when it happens, is a data-quality check upstream of the drift verdict,
not another threshold.

**A structural load change.** A large new interconnection, a big customer leaving,
a respondent boundary change. Level shift: target and the demand-lag features move
together, the model is biased from the first hour, performance alerts within a day.
This is the case the `--simulate-shift` injection models, and R1 fires.

**Slow decay — the hard one.** No single day crosses anything; the rolling MAE
climbs 2% a month. None of the distribution signals ever alert, and performance
crosses the +30% line months after the degradation started. The rolling-MAE chart
is the only place this is visible, which is why it is on the dashboard and why the
reference level is drawn on it. A trend test on the rolling series would catch it
sooner and is the obvious next threshold to add; it is deliberately not in yet,
because tuning a trend test against a fixture would be tuning it against nothing.

---

## 8. Limits, honestly

- **No real data.** Everything above about PJM is a prediction, not a finding.
- **The reference window is fixed, not adaptive.** 28 days, chosen because it
  covers four full weekly cycles. A production monitor would roll it forward as
  the model is retrained, and would keep several reference windows for different
  seasons. This one does not.
- **Only past weather is used.** Open-Meteo publishes a forecast and the lake
  already tags it `is_observed=False`. A production forecaster would legitimately
  feed tomorrow's forecast temperature in; this one does not, because that would
  make the "features use only data ≤ origin" claim depend on a second, unmodelled
  forecast, and the point of this repo is that the rigour claims are testable.
  Wiring it in is a later, explicit step.
- **The KS p-value is asymptotic**, not the exact combinatorial form. Accurate to
  ~1e-3 at these window sizes and checked against scipy; it would be the wrong
  choice for windows of tens of rows.
- **The retrain trigger has never been evaluated against a real episode.** Its
  rules are defensible and tested against injected shifts of known size. That is
  not the same as knowing the thresholds are right.
- **No alerting.** The verdict is written to a JSON file and drawn on a dashboard.
  Nothing pages anyone.
- **The dashboard is not deployed.** It builds to a static `dist/`; where it goes
  is a separate decision.

---

## 9. When the key lands

1. `EIA_API_KEY` into `.env` locally and into repository secrets.
2. `uv run python -m ingest --full-refresh` — two years of hourly PJM demand.
3. `uv run python -m models.train --source real` — real baseline, real LightGBM
   comparison, a champion trained on real data.
4. `uv run python -m pipeline.daily --source real` — every artifact regenerates
   with `"is_real": true`, the banner turns green, the watermark disappears.
5. Uncomment the `schedule:` block in `daily.yml` and let it run.

Then the numbers in this document become results, and this section gets deleted.

---

## 10. Where to look

| | |
|---|---|
| `README.md` | the design decisions, milestone by milestone |
| `docs/BLOCKED.md` | the EIA key, and the four steps to unblock it |
| `docs/spec.md` | the original brief |
| `metrics/drift_summary.md` | the current drift report, human-readable |
| `metrics/*.json` | the machine-readable artifacts the dashboard reads |
| `drift/stats.py` | PSI and KS, written out with every edge case named |
| `drift/trigger.py` | the retrain policy and why it is not a threshold |
| `pipeline/daily.py` | the six stages, and the in-sample guard from §5.1 |
