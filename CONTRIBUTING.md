# Contributing

Thanks for looking. This is a portfolio project, so it is small and opinionated —
but it is meant to be readable and runnable by a stranger, and if it is not, that
is a bug worth reporting.

## Setup

```bash
git clone https://github.com/rmonteiro-pereira/energy-forecast-drift
cd energy-forecast-drift
uv sync --extra dev
```

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/). For the dashboard
you also need **Node 20+** (developed on 24).

**No API key is needed and no network access is required.** Every entrypoint
falls back to a seeded synthetic fixture with a loud warning, and ingestion
degrades rather than failing when a source is unreachable. That is the normal
path today — see the README banner for why.

## Run everything

```bash
uv run pytest                     # 182 tests, no network        (~16 s)
uv run ruff check . && uv run ruff format --check .
uv run mypy                       # scoped -- see docs/adr/0002
uv run python -m pipeline.daily   # the whole loop               (~6 s)

cd dashboard && npm ci && npm test && npm run build
```

Exact transcripts of all of these, including the ones that fail on purpose, are
in [`docs/REPRODUCE.md`](docs/REPRODUCE.md).

## Before you open a PR

1. `uv run ruff check . && uv run ruff format --check .` — clean.
2. `uv run mypy` — clean.
3. `uv run pytest` — green.
4. `cd dashboard && npm test && npm run build` — if you touched `dashboard/`.

CI runs all of these plus smoke tests of the full pipeline. It must be green.

## House rules

These are not style preferences; breaking them breaks the point of the project.

**Never present a fixture number as a result.** While `is_real` is false, every
number here comes from `models/fixtures.py`. Artifacts carry the flag, the README
leads with a banner, the PNGs are watermarked, and the dashboard banner reads the
flag at render time. `tests/test_artifacts.py` fails the build if a published
artifact ever pairs `is_real: true` with synthetic provenance. Do not "simplify"
any of that into a constant.

**Never commit `mlruns/`, `mlflow.db`, parquet, `data/`, or anything over 5 MB.**
`metrics/` is the only published artifact directory, and it holds small JSON plus
two PNGs. CI enforces the size limit and the tracked-path rules.

**Explicit-path `git add` only.** No `git add .`, no `git add -A`. The data lake
is one `.gitignore` mistake away from the repo.

**No secrets in code, logs, commits or docs.** `EIA_API_KEY` lives in `.env` and
nowhere else. See [`SECURITY.md`](SECURITY.md).

**Tests cover the failure path, not just the happy one.** The drift alarm has a
test that it fires *and* a test that it stays quiet. The no-key guard has a test
that it exits 2 *and* that it wrote nothing. A test that only proves the good
case is half a test.

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

Start with [`docs/writeup.md`](docs/writeup.md) for how the pieces fit and which
bugs shaped them, and [`docs/adr/`](docs/adr/) for why the shape is what it is.

## Commit messages

Conventional-commit style, and the body explains **why**, not what — the diff
already says what. If a change fixes something subtle, say what the symptom was;
the commit log is the only place that survives.

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
