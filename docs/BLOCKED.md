# BLOCKED — real demand data is pending an EIA API key

**Status:** open
**Opened:** 2026-07-28 (during M0/M1)
**Blocks:** the real baseline MAE, the real LightGBM-vs-baseline delta, the live
cron, and every drift measurement from M4 onwards.

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

## Also gated on publishing the repo

`.github/workflows/daily.yml` is drafted but inactive. It needs a GitHub remote
plus `EIA_API_KEY` as a repository secret. The activation checklist is in the
header comment of that file. Worth doing early: the project's value is drift
accumulating week over week, so the sooner the cron starts, the more history
exists at interview time.
