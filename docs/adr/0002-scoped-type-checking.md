# 0002 — Type-check strictly in the logic core, loosely in the dataframe plumbing

**Status:** Accepted · **Date:** 2026-07

## Context

Adding `mypy` to CI over the whole package produced **258 errors in 15 files**.
168 of them were `[operator]`, and they were not describing the code. A single
expression such as

```python
frame.index.max() - pd.Timedelta(hours=window)
```

expands into a dozen errors of the form *"No overload variant of `__rsub__` of
`Timedelta` matches argument type `str`"* — one per member of the union that
`pandas-stubs` uses for a Series element it cannot narrow. The code is correct;
the stubs simply cannot express "this Series holds timestamps".

The distribution was lopsided: `pipeline/daily.py` (188) and
`drift/detectors.py` (30) accounted for **218 of the 258**, while
`drift/stats.py`, `drift/trigger.py`, `drift/config.py`, `ingest/http.py` and
`ingest/config.py` reported **zero**.

## Decision

Run mypy in CI over the whole package, with per-module configuration:

- **Strict** (`disallow_untyped_defs`, `disallow_incomplete_defs`,
  `warn_return_any`, `strict_equality`) on the modules whose correctness is
  *logical*: the PSI/KS statistics, the retrain policy, the thresholds, the HTTP
  and redaction layer, the fixture generator.
- **Checked but with the stub-noise codes off** (`operator`, `arg-type`,
  `union-attr`, `index`, `call-overload`) on the dataframe plumbing — so genuine
  problems there (undefined names, bad assignments, unreachable code, missing
  annotations) still fail the build.

Configuration lives in `pyproject.toml` with the reasoning inline.

## Rejected alternatives

**Strict mypy everywhere.** Rejected because the only way to reach zero is
`cast()` and `# type: ignore` at nearly every line that touches a Series. That
makes the code harder to read *and* makes the checker meaningless — a file that
is 30% ignore comments is not being checked, it is being silenced, and the next
real error hides among them.

**No type checker at all.** Rejected: it was leaving real defects on the floor.
Scoping the check surfaced a `Booster | None` that `serving/app.py` dereferenced
without a guard (an opaque `AttributeError` as a 500 if a service were ever used
unloaded), a `run_id: str | None` passed to `MlflowClient.get_run`, and a
`DailyPipeline` whose attributes were inferred as `None` because they were
initialised to `None` and never annotated. All three are now fixed properly, not
suppressed.

**Drop `pandas-stubs` so pandas resolves to `Any`.** Rejected because it silences
the noise by silencing everything — including the `arg-type` errors on our *own*
function signatures, which are the ones worth having. Per-module scoping keeps
those.

**`pyright` instead.** Not rejected on merit; mypy was chosen because the project
is already `uv`-managed with no Node requirement outside `dashboard/`, and adding
a second toolchain to the Python CI job to check Python was not worth it. Worth
revisiting if the strict set grows.

## Consequences

- CI enforces types, and `uv run mypy` is clean across all 34 source files.
- The strict list is a floor that can be raised module by module as the plumbing
  gets tidier — each promotion is a small, reviewable diff.
- A reader must consult `pyproject.toml` to know how strictly a given file is
  checked. Mitigated by keeping the two lists explicit rather than pattern-based,
  so the answer is greppable.
- Genuine `arg-type` bugs *inside* the plumbing modules will not be caught. This
  is the real cost and it is accepted knowingly.

## What would reverse this

Any of:

- `pandas-stubs` gaining the ability to narrow Series element types, which would
  remove the reason for the loose list entirely.
- A production defect traced to one of the disabled codes in a plumbing module —
  that would be evidence the trade is wrong, and the fix would be to promote that
  module to strict and pay the `cast()` cost deliberately.
- The plumbing shrinking. Much of `pipeline/daily.py`'s error count comes from
  long dataframe expressions; if those were extracted into small typed helpers,
  the module could join the strict list on its own merits.
