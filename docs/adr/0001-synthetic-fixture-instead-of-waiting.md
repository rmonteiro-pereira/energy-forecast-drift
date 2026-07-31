# 0001 — Ship a labelled synthetic fixture rather than wait for the API key

**Status:** Accepted · **Date:** 2026-07 · Supersedes nothing

## Context

The project forecasts hourly electricity demand for PJM and monitors the forecast
for drift. Demand comes from the EIA Open Data v2 API, which needs a free key.
The key had not been registered when the code was written, and registering it was
not something the build could do for itself.

Everything downstream — the backtest, the model comparison, the drift windows,
the monitor, the dashboard — needs a demand series to exist at all.

## Decision

Run the entire pipeline on a **seeded, date-anchored synthetic series**
(`models/fixtures.py`, seed `20260728`), and make the substitution impossible to
miss rather than merely disclosed:

- `"is_real": false` at the top level of every published artifact, plus a
  `warning` string the artifact carries itself;
- a `> [!CAUTION]` banner as the first element of the README;
- a rotated `SYNTHETIC FIXTURE — NOT REAL DATA` watermark on both committed PNGs;
- a red `role="alert"` banner on the dashboard, driven by the flag at render time
  rather than by copy;
- `--require-eia-key`, which makes the daily entrypoint exit before writing
  anything rather than publish fixture output;
- `tests/test_artifacts.py`, which fails the build if any artifact pairs
  `is_real: true` with synthetic provenance.

## Rejected alternatives

**Wait for the key before writing anything.** Rejected because it produces a
directory of untested code and a README making promises. Nothing would have been
exercised end to end, and the bugs that only appear when the whole chain runs —
including the in-sample monitoring bug in [0005](0005-monitor-refuses-in-sample-scoring.md),
which was found by staring at a suspicious number — would still be waiting.

**Use a different public dataset that needs no key.** Rejected because the point
of the project is a *live* feed accumulating drift over weeks. A static
historical CSV cannot drift; it would have meant building a different project and
describing it as this one.

**Mock the EIA client and assert against canned responses only.** Rejected
because it tests the client and nothing else. The interesting code is downstream
of ingestion, and a mock at the boundary leaves the panel, the backtest and the
drift windows unexercised on realistic shapes.

**Generate the fixture randomly per run.** Rejected because committed artifacts
would churn on every run, making a `git diff` of `metrics/` meaningless — and
because reproducibility is one of the few claims this repo *can* prove while the
data is fake. The seed and the fixed anchor date are what make
[`docs/REPRODUCE.md`](../REPRODUCE.md) §4 possible.

## Consequences

- **No number here is evidence of anything.** The −14.8% MAE improvement over the
  seasonal naive is fixture-against-fixture on a curve that is easier to fit than
  real load. It says the comparison plumbing works and nothing more.
- Every surface that displays a number carries provenance, which is more
  machinery than a project with real data would need.
- The reproducibility story is unusually strong as a side effect: the metrics come
  out byte-identical on a re-run.
- A reviewer may conclude the project is unfinished. It is — the data leg is.

## What would reverse this

The key arriving. At that point `--require-eia-key` becomes the normal path, the
backfill runs, and every artifact flips to `"is_real": true` on its own — no code
change, because the flag is computed from the panel provenance rather than set by
hand. The fixture stays as the CI smoke-test input, which is what it is good for.

This would also reverse if the fixture ever became load-bearing for a *claim*
rather than for execution — if someone quoted a fixture number as a result, the
right response would be to delete the numbers from the README entirely rather
than add another disclaimer.
