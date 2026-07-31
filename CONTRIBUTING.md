# Contributing

This project is about **honest measurement under drift**, not about forecast accuracy. A
change that improves a number without explaining why is worth less here than one that shows a
number was misleading.

It is small and opinionated, but it is meant to be readable and runnable by a stranger — and
if it is not, that is a bug worth reporting.

## Setup

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/). For the dashboard you also
need **Node 20+** (developed on 24).

```bash
git clone https://github.com/rmonteiro-pereira/energy-forecast-drift.git
cd energy-forecast-drift
uv sync --extra dev
```

**No API key is needed and no network access is required.** Without `EIA_API_KEY` the
pipeline falls back to a seeded synthetic fixture and says so, loudly, in every artifact it
writes; ingestion degrades rather than failing when a source is unreachable. That is the
normal path today — see the README banner for why.

## Running it

```bash
uv run python -m models          # walk-forward baseline
uv run python -m models.train    # LightGBM vs baseline, MLflow tracking
uv run python -m drift.run --out metrics/drift.json
uv run python -m pipeline.daily  # the whole loop               (~6 s)
uv run python -m serving         # FastAPI on :8000
```

## Tests, lint and types

```bash
uv run pytest                     # 208 tests, no network        (~20 s)
uv run ruff check . && uv run ruff format --check .
uv run mypy                       # scoped -- see docs/adr/0002
cd dashboard && npm ci && npm test && npm run build
```

All of these are enforced in CI. The ruff rule set is pinned deliberately so that a ruff
upgrade cannot silently change what CI enforces — if you bump it, expect to fix what it newly
finds in the same PR. Type checking is scoped rather than global, and the reasoning (with the
alternative that was rejected) is in [ADR 0002](docs/adr/0002-scoped-type-checking.md).

Exact transcripts of all of these, including the ones that fail on purpose, are in
[`docs/REPRODUCE.md`](docs/REPRODUCE.md).

## The rules that make the results mean anything

1. **Never set `is_real: true` without real data behind it.** The flag is written into every
   artifact, watermarked onto the plots, tagged on MLflow runs and checked by `/forecast`
   before it answers. Flipping it is a data event, not an edit. `tests/test_artifacts.py`
   fails the build if any published artifact pairs `is_real: true` with synthetic provenance.
2. **Do not weaken a leakage guard to make a test pass.** Leakage is blocked in several
   independent places and asserted by tests; if a guard fires, it is usually right.
3. **Drift thresholds live in config, not in code.** A threshold changed to silence an alarm
   needs a stated reason.
4. **Both injection tests must keep passing** — the alarm fires on an injected shift *and*
   stays silent without one. A detector that only ever fires is not a detector.
5. **Tests cover the failure path, not just the happy one.** The no-key guard has a test that
   it exits 2 *and* that it wrote nothing. A test that only proves the good case is half a
   test.
6. **Thresholds get boundary tests.** If you add or move a threshold, pin it just below,
   exactly on, and just above — `>=` and `>` differ at exactly one input, and that is the
   input nobody writes a test for. Mutation testing found this the hard way; see
   [`docs/MUTATION-TESTING.md`](docs/MUTATION-TESTING.md).
7. **No secrets in code, logs, commits or docs.** `EIA_API_KEY` has exactly two homes: `.env`
   locally (gitignored) and a GitHub Actions repository secret for CI. See
   [`SECURITY.md`](SECURITY.md).

## What not to commit

`mlruns/`, `mlflow.db`, model binaries, downloaded data, `.venv`, `dashboard/node_modules`,
`dashboard/dist`, anything over 5 MB. CI enforces the size limit and the tracked-path rules.

Regenerated `metrics/*.json` should only be committed when the change is *about* those
metrics — say so in the commit message.

**Explicit-path `git add` only.** No `git add .`, no `git add -A`. The data lake is one
`.gitignore` mistake away from the repo.

## Where things live

```
ingest/     API clients, polite HTTP, partitioned parquet store
features/   gapless panel, origin-stamped design matrix
models/     seasonal naive - LightGBM - walk-forward backtest - MLflow
drift/      own PSI + KS, four drift types, the retrain policy
pipeline/   daily.py: the six-stage entrypoint daily.yml calls
serving/    FastAPI /forecast from the registry alias
dashboard/  Vite + React + ECharts over metrics/*.json
docs/adr/   architecture decisions, including the rejected alternatives
```

Start with [`docs/writeup.md`](docs/writeup.md) for how the pieces fit and which bugs shaped
them, and [`docs/adr/`](docs/adr/) for why the shape is what it is.

## Pull requests

- Branch from `main`; never commit to it directly.
- [Conventional Commits](https://www.conventionalcommits.org/), and the body explains **why**,
  not what — the diff already says what. If a change fixes something subtle, say what the
  symptom was; the commit log is the only place that survives.
- Explain what you measured.
- `pytest`, `ruff check .`, `ruff format --check .` and `mypy` green before opening.

```
feat(drift): report calendar features but exclude them from the verdict

A 28-day reference against a 14-day current window necessarily spans
different months, so `month` scores PSI ~7 on every healthy run. Letting a
deterministic function of the timestamp drive the alarm would mean firing
every single day.
```

## Reporting a problem

Open an issue with what you ran, what happened, and what you expected. If it is
security-related, use a private advisory instead — [`SECURITY.md`](SECURITY.md).
