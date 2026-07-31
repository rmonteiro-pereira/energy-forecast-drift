## What and why

<!-- What changed, and what problem it solves. The diff says what; this says why. -->

## Checks

<!-- CI runs all of these. Ticking them before you push is faster than a red build. -->

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run mypy`
- [ ] `uv run pytest`
- [ ] `cd dashboard && npm test && npm run build` *(only if `dashboard/` changed)*

## Honesty checklist

<!-- These are the rules that make this repo mean anything. See CONTRIBUTING.md. -->

- [ ] No fixture number is presented as a result. Every `metrics/*.json` still
      carries `"is_real": false`, and `tests/test_artifacts.py` passes.
- [ ] No secret, credential, private address or absolute local path is added —
      including in docs.
- [ ] Nothing over 5 MB, and no `mlruns/`, `*.db`, parquet, `data/`,
      `node_modules/` or `dist/` is staged.
- [ ] Staged with explicit paths (no `git add .` / `git add -A`).

## Decisions

<!-- If this changes an architectural choice, add or amend an ADR in docs/adr/
     and state the alternative you rejected. Delete this section if not. -->
