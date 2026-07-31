# Reproducing this repository

> **⚠️ Reminder before any number below:** there is no EIA API key, so the demand
> series is a **seeded synthetic fixture**. Everything here demonstrates that the
> pipeline runs and that it runs *deterministically*. None of it is a benchmark.

Every block on this page is **real captured output**, pasted from the run
recorded at the top of each section. Nothing is retyped from memory or tidied up.
Where a command printed a warning, the warning is still there.

**One deliberate edit:** absolute paths to the machine this ran on are shortened
to `<repo>` (and `metrics\forecast.json` in place of the full path the logger
prints). Nothing else is altered — no number, no warning, no exit code. The
publication scan flags absolute local paths as a leak, and a document that
exempted itself from its own repo's scan would be the wrong kind of exception.

**Environment:** Windows 11, Python 3.11.12, Node 22, `uv`, all on `main` at
commit `e988a0e`, run 2026-07-31.

> **The test counts below are the ones that run printed, and they are lower than
> today's.** This page is a transcript pinned to `e988a0e`, where the suite was
> **178 passed / 2 skipped**. The suite has grown since — the type pass, the
> CodeRabbit fixes and the mutation-testing work all added tests. Re-running
> every command to refresh the numbers would replace a real transcript with a
> newer real transcript and change nothing about what it demonstrates, so the
> original is kept. An earlier version of this very note quoted a "current"
> count that had itself gone stale, which is the fate of every second copy of a
> live number — so the current count is stated once, in the README, where
> `tests/test_doc_claims.py` collects the suite and fails if the prose drifts.

---

## 0. Setup

```bash
git clone <this repo> && cd energy-forecast-drift
uv sync --extra dev
```

No `.env` is needed to reproduce anything on this page. `EIA_API_KEY` is unset
throughout, which is exactly the condition the repository currently documents.

---

## 1. The test suite

```console
$ uv run pytest -p no:warnings -v

============================= test session starts =============================
platform win32 -- Python 3.11.12, pytest-9.1.1, pluggy-1.6.0
rootdir: <repo>                       # local absolute path shortened, see note below
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.14.2, Faker-40.36.0
collected 180 items

tests\test_artifacts.py ...........ss..........                          [ 12%]
tests\test_backtest.py ........                                          [ 17%]
tests\test_baseline.py .....                                             [ 20%]
tests\test_clients.py ...........                                        [ 26%]
tests\test_drift_detectors.py .............                              [ 33%]
tests\test_drift_run.py ...........                                      [ 39%]
tests\test_drift_stats.py .............                                  [ 46%]
tests\test_drift_trigger.py ................                             [ 55%]
tests\test_features_build.py .............                               [ 62%]
tests\test_lgbm.py ............                                          [ 69%]
tests\test_panel.py .....                                                [ 72%]
tests\test_pipeline_daily.py .................                           [ 81%]
tests\test_serving.py ............                                       [ 88%]
tests\test_store.py ........                                             [ 92%]
tests\test_workflows.py .............                                    [100%]

======================= 178 passed, 2 skipped in 19.97s =======================
```

**178 passed, 2 skipped, exit code 0.** No network access — the API clients are
exercised against `httpx.MockTransport`.

The two skips are deliberate and reported, not silent:

```console
$ uv run pytest tests/test_artifacts.py -q -rs

...........ss..........                                                  [100%]
=========================== short test summary info ===========================
SKIPPED [1] tests\test_artifacts.py:83: monitor.json carries no nested provenance block to cross-check
SKIPPED [1] tests\test_artifacts.py:83: pipeline.json carries no nested provenance block to cross-check
```

`monitor.json` and `pipeline.json` inherit their provenance from the run rather
than carrying a nested `data` block, so the cross-check has nothing to compare
against. They are still covered by the other three assertions in that file.

## 2. Lint

```console
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
58 files already formatted
```

Both exit 0.

---

## 3. The daily pipeline, end to end

This is the single entrypoint `daily.yml` calls. It runs six stages and rewrites
`metrics/`.

```console
$ uv run python -m pipeline.daily

22:42:30 WARNING ingest | EIA_API_KEY not set -> skipping the demand leg. Register free at https://www.eia.gov/opendata/register.php, put EIA_API_KEY=... in .env and re-run. See docs/BLOCKED.md.
22:42:30 INFO    ingest.openmeteo | Open-Meteo recent philadelphia_pa: past_days=5 (+ today)
22:42:31 INFO    httpx | HTTP Request: GET https://api.open-meteo.com/v1/forecast?latitude=39.9526&longitude=-75.1652&hourly=temperature_2m&past_days=5&forecast_days=1&timezone=UTC "HTTP/1.1 200 OK"
22:42:31 INFO    ingest.store | weather_hourly: received 121 row(s) -> +48 new, ~73 revised, 792 total across 1 partition(s)
22:42:31 INFO    pipeline.daily | [ingest] ok in 1.6s
22:42:31 WARNING models.data | No real demand in the lake -> falling back to the SYNTHETIC fixture.
22:42:31 INFO    pipeline.daily | [features] degraded in 0.0s
22:42:34 INFO    drift.windows | Fitted the drift reference booster on 12440 train row(s).
22:42:34 INFO    pipeline.daily | [score] ok in 3.3s
22:42:34 INFO    pipeline.daily | wrote metrics\forecast.json
22:42:35 INFO    pipeline.plots | wrote metrics\forecast_vs_actual.png
22:42:35 INFO    pipeline.daily | [forecast] ok in 0.2s
22:42:35 INFO    pipeline.daily | wrote metrics\monitor.json
22:42:35 INFO    pipeline.plots | wrote metrics\rolling_mae.png
22:42:35 INFO    pipeline.daily | [monitor] ok in 0.1s
22:42:39 INFO    pipeline.daily | wrote metrics\drift.json
22:42:39 INFO    pipeline.daily | [drift] ok in 4.0s
22:42:39 INFO    pipeline.daily | wrote metrics\pipeline.json

   ingest     ok           1.6s
 ~ features   degraded     0.0s
   score      ok           3.3s
   forecast   ok           0.2s
   monitor    ok           0.1s
   drift      ok           4.0s

drift verdict: WATCH (R4_watch)
artifacts:     drift.json, drift_summary.md, forecast.json, forecast_vs_actual.png, monitor.json, pipeline.json, rolling_mae.png

!!! EVERY NUMBER IN THIS RUN IS FIXTURE-DERIVED, NOT A RESULT.
!!! These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. They are a smoke test of the pipeline, NOT a benchmark. The real baseline is pending the EIA API key — see docs/BLOCKED.md.
```

Exit code 0, 5.9 s wall clock. Three things in that transcript are worth
pointing at:

- **The weather leg is real.** `HTTP/1.1 200 OK` against `api.open-meteo.com`,
  121 rows received, 48 new and 73 revised. The revision overwrite is the
  incremental-store behaviour working on live data.
- **`features` is `degraded`, not `ok`.** That is the fixture fallback announcing
  itself. Ingestion is the only stage permitted to degrade; anything after it
  failing is fatal.
- **The run ends by disowning its own numbers.** The last two lines are printed
  by the pipeline itself, not added here.

### 3.1 The same run refuses to publish without a key

```console
$ uv run python -m pipeline.daily --require-eia-key --source real

EIA_API_KEY is not set.

  This pipeline was started with --require-eia-key, which means it refuses to
  publish metrics derived from the synthetic fixture. Register a free key at
  https://www.eia.gov/opendata/register.php and either put EIA_API_KEY=... in
  .env locally, or add it as a repository secret named EIA_API_KEY.

  Full instructions: docs/BLOCKED.md
  To run against the fixture instead, drop --require-eia-key.

$ echo $?
2
```

**Exit code 2, and no file was written** — the check runs before any artifact is
touched. This is the flag `.github/workflows/daily.yml` passes, which is what
makes it structurally impossible for the cron to publish fixture numbers as
though they were data. CI asserts both halves: the exit code *and* that
`metrics/` is untouched.

---

## 4. Determinism: the numbers reproduce exactly

The fixture is seeded (`20260728`) and anchored to a fixed end date, so re-running
the model entrypoints must produce byte-identical metrics. That is the property
that makes committed artifacts reviewable — a diff should show timestamps moving
and nothing else.

```console
$ uv run python -m models          # M1, the seasonal-naive baseline

...
| 24 | 2,844 | 3.46 | 3,623 | -178 | 56 |

overall MAE=2,559 MWh  MAPE=2.77%  (56 folds x 24 horizons)
wrote metrics\baseline.json and metrics\baseline_table.md
```

```console
$ uv run python -m models.train    # M2+M3, LightGBM vs baseline + MLflow

...
| 24 | 2,844 | 2,602 | -242 | -8.5 |

seasonal naive  MAE      2,559 MWh   MAPE 2.77%
LightGBM        MAE      2,181 MWh   MAPE 2.38%
delta           MAE       -378 MWh   (-14.78%), LightGBM wins 23/24 horizons

!!! THIS DELTA IS FIXTURE-DERIVED, NOT A RESULT.
!!! These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. They are a smoke test of the pipeline, NOT a benchmark. The real baseline is pending the EIA API key — see docs/BLOCKED.md.
wrote metrics\model.json and metrics\model_table.md
```

These figures are identical, digit for digit, to the ones committed two days
earlier — `2,559 / 2,181 / −378 / −14.78% / 23 of 24`. Re-running the whole chain
produced this diff and nothing else:

```console
$ git diff --stat metrics/
 metrics/drift.json       | 10 +++++-----
 metrics/drift_summary.md |  2 +-
 metrics/forecast.json    |  8 ++++----
 metrics/monitor.json     |  8 ++++----
 metrics/pipeline.json    | 34 +++++++++++++++++-----------------
 5 files changed, 31 insertions(+), 31 deletions(-)
```

Every one of those changed lines is a timestamp or a registry version. **No
metric value moved.** Both PNGs came out byte-identical and do not appear in the
diff at all.

The registry version bump is worth a note: it resolves a real inconsistency. The
previously committed artifacts recorded champion `v2` while the local MLflow
registry had moved on to `v3`, because `mlruns/` is gitignored and so a
`git checkout` of `metrics/` could not roll the registry back. Running the full
chain — `models.train` then `pipeline.daily` — realigns everything on one
version:

```console
$ python -c "..."   # the registry version each artifact records
model.json     4
drift.json     4
monitor.json   4
forecast.json  4
pipeline.json  4
```

---

## 5. Serving

Started with `uv run python -m serving` (uvicorn on 127.0.0.1:8241) and queried
over real HTTP — not `TestClient`.

```console
$ curl 'http://127.0.0.1:8241/health'
{"status":"ok","model_source":"mlflow_registry","model_version":"4","is_real":false,"panel_rows":4801}
```

```console
$ curl 'http://127.0.0.1:8241/forecast?max_horizon=3'
{
  "generated_at_utc": "2026-07-31T01:45:45+00:00",
  "origin_utc": "2026-07-28T01:00:00+00:00",
  "units": "MWh",
  "is_real": false,
  "warning": "These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. They are a smoke test of the pipeline, NOT a benchmark. The real baseline is pending the EIA API key — see docs/BLOCKED.md.",
  "model": {
    "source": "mlflow_registry",
    "uri": "models:/energy-demand-forecaster@champion",
    "registered_model": "energy-demand-forecaster",
    "alias": "champion",
    "version": "4",
    "run_id": "080189369e3f451da51bd5884de2731b",
    "trained_on_real_data": false,
    "data_kind": "synthetic_fixture",
    "train_data_end_utc": "2026-07-28T00:00:00+00:00",
    "n_features": 20
  },
  "data": {
    "kind": "synthetic_fixture",
    "is_real": false,
    "generator": "models.fixtures.synthetic_series",
    "seed": 20260728,
    "anchor_end_utc": "2026-07-28T00:00:00+00:00",
    "label": "SYNTHETIC — NOT REAL DATA"
  },
  "horizons": 3,
  "forecast": [
    {"horizon_h": 1, "target_utc": "2026-07-28T02:00:00+00:00", "forecast_mwh": 78091.6, "actual_mwh": null},
    {"horizon_h": 2, "target_utc": "2026-07-28T03:00:00+00:00", "forecast_mwh": 75385.0, "actual_mwh": null},
    {"horizon_h": 3, "target_utc": "2026-07-28T04:00:00+00:00", "forecast_mwh": 75414.7, "actual_mwh": null}
  ]
}
```

The forecast values are fixture output like everything else. What matters in
that response is that a consumer **cannot receive the numbers without also
receiving `is_real: false` and the warning** — the provenance is not an optional
field a client can forget to read.

### 5.1 The origin guard, both directions

`build_design_matrix` will happily emit NaN features for an origin with no
history behind it, and LightGBM will turn those into a confident-looking number.
`/forecast` refuses instead:

```console
$ curl -i 'http://127.0.0.1:8241/forecast?origin_utc=2020-01-01T00:00:00Z'
HTTP/1.1 422
{"detail":"Origin 2020-01-01T00:00:00+00:00 has less than 672h of history behind it. The earliest origin this panel supports is 2026-02-06T00:00:00+00:00."}

$ curl -i 'http://127.0.0.1:8241/forecast?origin_utc=2030-01-01T00:00:00Z'
HTTP/1.1 422
{"detail":"Origin 2030-01-01T00:00:00+00:00 is beyond the information set — the last observed hour supports origins up to 2026-07-28T01:00:00+00:00."}
```

Both bounds return 422 **with the valid range in the message**, rather than a
number nobody should trust.

---

## 6. The dashboard

```console
$ cd dashboard
$ rm -rf node_modules
$ npm ci

npm WARN deprecated whatwg-encoding@3.1.1: Use @exodus/bytes instead for a more spec-conformant and faster implementation
added 181 packages, and audited 182 packages in 18s
29 packages are looking for funding
```

Exit code 0, from a clean `node_modules`.

```console
$ npm test

 RUN  v2.1.9 <repo>/dashboard

 ✓ src/components.test.tsx (4 tests) 50ms

 Test Files  1 passed (1)
      Tests  4 passed (4)
   Duration  2.24s
```

```console
$ npm run build

> tsc -b && vite build

vite v5.4.21 building for production...
transforming...
✓ 592 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.62 kB │ gzip:   0.38 kB
dist/assets/index-CSzcyafK.css    5.85 kB │ gzip:   1.84 kB
dist/assets/index-_xznmLxe.js   694.07 kB │ gzip: 230.19 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
...
✓ built in 2.85s
```

**Exit code 0.** The chunk-size warning is left in deliberately: ECharts is a
large library and this is a single-page dashboard with no routing, so
code-splitting would buy nothing. 230 KB gzipped is the honest cost.

```console
$ ls -R dist
dist/index.html                621
dist/assets/index-_xznmLxe.js  694763
dist/assets/index-CSzcyafK.css 5850
dist/data/baseline.json        5808
dist/data/drift.json           67848
dist/data/forecast.json        94967
dist/data/model.json           18756
dist/data/monitor.json         12957
dist/data/pipeline.json        4354
```

`dist/data/` is the copy of `metrics/*.json` the build makes, which is why the
built site can be pointed at fresher metrics without a rebuild.

### 6.1 Proving the banner reads the flag

The claim is that `ProvenanceBanner` decides what it renders from the artifact
and from nothing else. It is verified twice, in two different ways.

**Automatically**, by `dashboard/src/components.test.tsx` — four cases that
render the component with identical props and only `is_real` flipped, asserting
the states differ in substance (`role="alert"` present or absent, different
heading, the word "benchmark" present or absent) rather than in wording.

**Visually**, by serving two copies of the *same* build:

```bash
python -m http.server 8231 --directory dashboard/dist            # is_real = false
cp -r dashboard/dist /tmp/flagdemo && <flip is_real in /tmp/flagdemo/data/*.json>
python -m http.server 8232 --directory /tmp/flagdemo             # is_real = true
```

```console
metrics/ (committed)     is_real = False
dashboard/dist/ (built)  is_real = False
flagdemo copy            is_real = True
```

Screenshotted headless at 1400×1500. The two pages are byte-identical bundles
showing byte-identical numbers — `2,534 MWh`, `9.0%`, `2.81%`, verdict `Watch`
— and differ in exactly one element:

*(Those screenshots were taken before the registry realignment in §4, so they
show champion `v2` where a fresh build now shows `v4`. Both pages showed the
same version as each other, which is the only thing the comparison depends on.)*

| `is_real` | Banner |
|---|---|
| `false` | red, `role="alert"`, **"Synthetic data — these are not real forecasts, and not a benchmark"**, quoting the artifact's own `warning` field |
| `true` | green, no alert role, **"Live data"**, naming the source as `eia_api_v2` |

The flip is done on a **copy** and never on `metrics/`. Editing `metrics/` by
hand would put a false `is_real` into a committed artifact, which is the exact
failure this whole apparatus exists to prevent — and which
`tests/test_artifacts.py` would now catch.

---

## 7. The architecture diagram renders

The mermaid block in `README.md` is not assumed to parse; it is rendered.

```console
$ npx --yes @mermaid-js/mermaid-cli --version
11.16.0

$ npx --yes @mermaid-js/mermaid-cli -i diagram.mmd -o diagram.png -w 1800 -b white
Generating single mermaid chart

$ echo $?
0
```

Exit code 0, 51 KB PNG produced, inspected visually: 6 subgraphs, all node
references resolve, no orphan edges. The rendered output is not committed —
GitHub renders the fenced block natively, and committing a second copy of the
same diagram guarantees the two drift apart.

---

## 8. What you cannot reproduce

Stated plainly, because a reproducibility document that omits its own gaps is
worth less than nothing:

| | Why |
|---|---|
| **Any real demand number** | There is no EIA API key. Not a code problem: `ingest/eia.py` is complete and tested, and has simply never been given a key. |
| **A real drift episode** | Drift is measured between two windows of real history. There is no real history. What the repo can show is the mechanism, and an injected shift proving the alarm responds to it. |
| **The exact MLflow run ids above** | Every `models.train` run registers a new version, so `run_id` and `version` are local to your machine. The *metrics* reproduce exactly; the run identifiers do not. |
| **Byte-identical `metrics/pipeline.json`** | It records wall-clock durations and a UTC timestamp. The metric values inside are deterministic; the timings are not. |
| **The weather rows exactly** | Open-Meteo is live, so `rows_added` / `rows_revised` depend on when you run it. This is the one input that is genuinely real, and therefore the one that genuinely moves. |

---

## 9. Summary

| Check | Command | Result |
|---|---|---|
| Python tests | `uv run pytest` | **178 passed, 2 skipped** — exit 0 |
| Lint | `uv run ruff check .` | **All checks passed** — exit 0 |
| Format | `uv run ruff format --check .` | **58 files already formatted** — exit 0 |
| Daily pipeline | `uv run python -m pipeline.daily` | **6 stages, verdict WATCH** — exit 0, 5.9 s |
| Fail-fast guard | `... --require-eia-key --source real` | **exit 2, nothing written** |
| Baseline | `uv run python -m models` | exit 0, artifacts reproduce exactly |
| Train + registry | `uv run python -m models.train` | exit 0, artifacts reproduce exactly |
| Serving | `curl /forecast` over uvicorn | 200 with provenance; 422 on both origin bounds |
| Dashboard install | `npm ci` | exit 0 from clean `node_modules` |
| Dashboard tests | `npm test` | **4 passed** — exit 0 |
| Dashboard build | `npm run build` | exit 0, `dist/` produced |
| Diagram | `mermaid-cli` render | exit 0 |

And the standing caveat, one last time: **every metric above is fixture-derived.
None of it is a benchmark.**
