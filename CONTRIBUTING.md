# Contributing

This project is about **honest measurement under drift**, not about forecast accuracy. A
change that improves a number without explaining why is worth less here than one that shows a
number was misleading.

## Setup

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rmonteiro-pereira/energy-forecast-drift.git
cd energy-forecast-drift
uv sync
```

No API key is needed to run anything: without `EIA_API_KEY` the pipeline falls back to a
seeded synthetic fixture and says so, loudly, in every artifact it writes.

## Running it

```bash
uv run python -m models          # walk-forward baseline
uv run python -m models.train    # LightGBM vs baseline, MLflow tracking
uv run python -m drift.run --out metrics/drift.json
uv run python -m pipeline.daily  # the whole loop
uv run python -m serving         # FastAPI on :8000
```

## Tests and lint

```bash
uv run pytest -q
uv run ruff check .
```

Both are enforced in CI. The ruff rule set is pinned deliberately so that a ruff upgrade
cannot silently change what CI enforces — if you bump it, expect to fix what it newly finds
in the same PR.

## The rules that make the results mean anything

1. **Never set `is_real: true` without real data behind it.** The flag is written into every
   artifact, watermarked onto the plots, tagged on MLflow runs and checked by `/forecast`
   before it answers. Flipping it is a data event, not an edit.
2. **Do not weaken a leakage guard to make a test pass.** Leakage is blocked in several
   independent places and asserted by tests; if a guard fires, it is usually right.
3. **Drift thresholds live in config, not in code.** A threshold changed to silence an alarm
   needs a stated reason.
4. **Both injection tests must keep passing** — the alarm fires on an injected shift *and*
   stays silent without one. A detector that only ever fires is not a detector.

## What not to commit

`mlruns/`, `mlflow.db`, model binaries, downloaded data, `.venv`, `dashboard/node_modules`,
`dashboard/dist`, anything over 5 MB. Regenerated `metrics/*.json` should only be committed
when the change is *about* those metrics — say so in the commit message.

## Pull requests

- Branch from `main`; never commit to it directly.
- [Conventional Commits](https://www.conventionalcommits.org/).
- Explain **why**, and state what you measured.
- `pytest -q` and `ruff check .` green before opening.
