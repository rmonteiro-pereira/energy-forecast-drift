# BLOCKED — no model has been trained on the real demand data

**Status:** the key landed 2026-08-01 and the demand block **closed**. What is
left is one training run. The title of this file used to say "real demand data is
pending an EIA API key"; that is no longer what it is about.
**Opened:** 2026-07-28 (during M0/M1)
**Still blocks:** the real baseline MAE and the real LightGBM-vs-baseline delta,
because no real-data model has been trained or registered yet.
**No longer blocks:** ingestion and the cron. Both are proven, not assumed —
see below.

## What the first real run proved (2026-08-01, run 30718525099)

`daily.yml` ran against the live API for the first time in the project's
history. `HTTP/1.1 200 OK` from `api.eia.gov`, **17,520 hourly PJM demand
records** over a two-year window in four paged calls, plus 17,522 rows of
Open-Meteo archive. `ingest`, `features`, `score`, `forecast`, `monitor` and
`drift` all returned `ok`.

**And it published nothing.** The final step pushed at `main`, which is
protected and requires the `test` check, and `github-actions[bot]` is not an
admin — `GH006: Protected branch update failed`. The commit was built on the
runner and died with it. That step now opens a PR instead.

That publication gap has since closed: the rewritten step opened a PR, it merged,
and `forecast.json`, `monitor.json`, `drift.json` and `pipeline.json` on `main`
now carry `"is_real": true` — along with both PNGs, which lost their watermark
because `pipeline/plots.py` only stamps a fixture.

One thing from that run remains true:

- the run logged `No registry champion` — `mlflow.db` is restored from cache and
  never seeded, so nothing has trained on real data yet. Step 4 below is what
  fixes that, and it has not been run. There is now a workflow that does it on a
  runner instead — `.github/workflows/train.yml`, dispatched by hand — which
  also publishes the registry as a release asset so it stops living only in an
  evictable cache. Unlike `data/`, which a full refresh re-pulled in 43 seconds,
  promotion decisions and lineage cannot be re-derived from anywhere.

---

## What is blocked

**Both ingestion legs run.** Open-Meteo needs no key and pulls observed
temperature for nine metros plus the archived day-ahead forecast. The EIA leg has
a key and has pulled 17,520 hourly PJM rows with no gaps. Neither is blocked.

What is blocked is **one training run against that data.** Nothing has called
`models.train --source real`, so there is no `@champion`, `served_model.source` is
`"none"`, and the monitor scores with a booster it fitted on its own training
window rather than a promoted model.

## Consequence right now

`python -m models` and `python -m models.train` have not been re-run since the
lake filled, so they still hold output from the **seeded synthetic fixture**
(`models/fixtures.py`):

- `metrics/baseline.json` and `metrics/model.json` carry `"is_real": false` and a
  warning string, and the MLflow runs are tagged `is_real=false`;
- **the LightGBM-vs-baseline delta in the README is not a result.** It is a smoke
  test, on a fixture, and the README says so beside the number. Do not quote it.

Note the asymmetry, because it is the whole state of the project: everything that
*measures what happened* is real, and everything that *compares one model to
another* is not.

## The foundation lane waits on the same key

`python -m foundation` is the dispatch run for the zero-shot-vs-GBM comparison
(`docs/rfc/rfc-foundation-vs-gbm.md`). Everything it needs exists and is tested —
the arms, the gates, the cost accounting, the interval, the adapter against real
Chronos-Bolt weights — **except the demand panel**. It refuses `--source real`
with the same message as every other entrypoint here, and it refuses to write
`metrics/foundation.json` from a fixture, so there is no way to produce that file
by accident:

```
$ uv run python -m foundation --source real --tsfm chronos
error: No EIA demand in the lake. Run `uv run python -m ingest` first
       (requires EIA_API_KEY — see docs/BLOCKED.md), or use `--source synthetic`.
```

With the key in `.env` and the lake filled, the run is:

```bash
OMP_NUM_THREADS=1 uv sync --extra dev --extra foundation --frozen
OMP_NUM_THREADS=1 uv run python -m foundation --source real --tsfm chronos --arms all
```

Two things about that command are load-bearing. `--extra foundation` installs
torch and is **never** what CI installs. `OMP_NUM_THREADS=1` is checked, not
assumed: the run refuses to start without it, because `num_threads` in the
LightGBM parameters does not serialise OpenMP and the cost table would then
describe a machine nobody configured.

Against the synthetic fixture the same command runs today and proves the
plumbing — and nothing else. Those numbers are a smoke test; the comparison is
only a comparison on the real panel.

## Unblocking it

**Steps 1–3 are done.** The key is registered and stored in repository secrets,
and the lake holds two years of hourly PJM demand. They are kept below because a
stranger cloning this repo starts where the project started, with no key.

**The only step left is 4**, and the fastest way to run it is not locally at all:
dispatch `.github/workflows/train.yml` from the Actions tab. It ingests, trains
with `--source real`, promotes to `@champion` only on a genuine win, and publishes
the registry as a release asset so it stops living in an evictable cache.

1. ~~**Register**~~ *(done 2026-08-01)* at
   <https://www.eia.gov/opendata/register.php> — free, no card, the key arrives by
   email in seconds.
2. ~~**Store it**~~ *(done — it is in repository secrets as `EIA_API_KEY`)*:
   ```bash
   cp .env.example .env
   # then edit .env:  EIA_API_KEY=<the key from the email>
   ```
   `.env` is gitignored. Never paste the key into a file that is tracked, into
   a commit message, or into a log.
3. ~~**Backfill**~~ *(done — 17,520 rows, 0 missing hours)*:
   ```bash
   uv run python -m ingest          # ~2 years of hourly PJM demand, first run
   uv run python -m ingest          # re-run: should report +0 new rows
   ```
4. **← THE REMAINING STEP. Recompute the real baseline and the real model
   comparison**, then commit:
   ```bash
   uv run python -m models --source real          # metrics/baseline.json
   uv run python -m models.train --source real    # metrics/model.json + MLflow
   git add metrics/baseline.json metrics/baseline_table.md \
           metrics/model.json metrics/model_table.md
   git commit -m "feat(metrics): real baseline and LightGBM delta on PJM demand"
   ```
   `--source real` fails loudly rather than falling back, so a green run proves
   the numbers came from the API. Both artifacts flip to `"is_real": true`.

   **That run also answers a question nothing else can.** Since 2026-08-01 the
   model has forecast-weather features — what the day-before model run predicted
   for the target hour, from nine metros across the PJM footprint. Whether they
   help is not knowable on the fixture, whose synthetic temperature is nearly
   implied by the calendar; there, the ablation correctly reports them as
   *harmful*. `models.train` re-scores the identical protocol without those
   columns and writes the delta to `ablation.forecast_weather` in
   `metrics/model.json`. On real demand that number is the first honest evidence
   of whether forward-looking weather is worth its ingestion cost. It roughly
   doubles the LightGBM half of the run; `--skip-ablation` opts out.

Then update the README's M1 and M2 tables from `metrics/baseline_table.md` and
`metrics/model_table.md`, rewrite the "still synthetic" half of the README banner
(the "drift numbers are real" half already stands), retire the two SYNTHETIC
`<details>` blocks, and close this file.

## The cron — no longer gated, but not yet scheduled

`.github/workflows/daily.yml` has the remote and the secret it was waiting for,
and has run green against real data once. Two items are left on its checklist,
both in the header comment of that file: the `schedule:` block is still
commented out, and the repo setting *Allow GitHub Actions to create and approve
pull requests* is off, which is what the publish step needs to open its PR
unattended. Without it the step still pushes the branch and degrades to a
warning carrying the link, so nothing is lost — it just needs a click.

Worth doing early for the reason it always was: the project's value is drift
accumulating week over week, so the sooner the cron starts, the more history
exists at interview time.
