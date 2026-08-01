# BLOCKED — real demand data is pending an EIA API key

**Status:** the key landed 2026-08-01. The block moved; it did not close.
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

Two things therefore remain true even though the key works:

- every `metrics/*.json` in this repository still carries `"is_real": false`;
- the run logged `No registry champion` — `mlflow.db` is restored from cache and
  never seeded, so nothing has trained on real data yet. Step 4 below is what
  fixes that, and it has not been run.

---

## What is blocked

The **Open-Meteo** leg is complete and running: `uv run python -m ingest` pulls
real hourly temperature today, incrementally and idempotently.

The **EIA** leg — hourly electricity demand for PJM, which is the target
variable of the whole project — cannot run because no `EIA_API_KEY` has been
registered yet. The client is finished, not stubbed: respondent discovery,
paging, retry/backoff, revision handling and parsing are all implemented and
covered by tests against a mock transport. It runs the moment the key exists.

## Consequence right now

Without demand history there is no real baseline to beat, so `python -m models`
and `python -m models.train` both fall back to a **seeded synthetic fixture**
(`models/fixtures.py`). That keeps the pipeline runnable and testable, and
nothing more:

- every artifact they produce carries `"is_real": false` and a warning string;
- `metrics/baseline.json` and `metrics/model.json` currently hold **synthetic**
  numbers, and the MLflow runs are tagged `is_real=false`;
- **neither the MAE nor the LightGBM-vs-baseline delta in the README is a
  result.** They are smoke tests. Do not quote them anywhere.

## Unblocking it — 4 steps, ~5 minutes

1. **Register** at <https://www.eia.gov/opendata/register.php> — free, no card,
   the key arrives by email in seconds.
2. **Store it locally**:
   ```bash
   cp .env.example .env
   # then edit .env:  EIA_API_KEY=<the key from the email>
   ```
   `.env` is gitignored. Never paste the key into a file that is tracked, into
   a commit message, or into a log.
3. **Backfill**:
   ```bash
   uv run python -m ingest          # ~2 years of hourly PJM demand, first run
   uv run python -m ingest          # re-run: should report +0 new rows
   ```
4. **Recompute the real baseline and the real model comparison**, then commit:
   ```bash
   uv run python -m models --source real          # metrics/baseline.json
   uv run python -m models.train --source real    # metrics/model.json + MLflow
   git add metrics/baseline.json metrics/baseline_table.md \
           metrics/model.json metrics/model_table.md
   git commit -m "feat(metrics): real baseline and LightGBM delta on PJM demand"
   ```
   `--source real` fails loudly rather than falling back, so a green run proves
   the numbers came from the API. Both artifacts flip to `"is_real": true`.

Then update the README tables from `metrics/baseline_table.md` and
`metrics/model_table.md`, delete the pending-key banner and the two SYNTHETIC
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
