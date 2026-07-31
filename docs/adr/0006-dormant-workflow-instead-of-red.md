# 0006 — Let the daily workflow go dormant rather than fail red

**Status:** Accepted · **Date:** 2026-07 · Amends [0001](0001-synthetic-fixture-instead-of-waiting.md)

## Context

`daily.yml` runs one command: `pipeline.daily --require-eia-key --source real`.
That flag makes a missing key a hard failure — exit 2, with printed instructions,
**before a single byte is written**. The reasoning was sound: a cron that quietly
publishes fixture numbers as though they were data is the worst thing this repo
could do, so it was made impossible rather than warned about.

Then the repository went public, and the calculus changed. The Actions tab is now
part of what a visitor reads. Anyone clicking "Run workflow" — the only way to
run it, since the schedule is still commented out — got a **red X**. A red X on a
project's only scheduled workflow says *this is broken*. The truth is *this is
waiting for a free API key*, which the README already explains at length.

## Decision

Add a preflight step that checks whether `EIA_API_KEY` is configured, and gate
every subsequent step on its output:

- **No key** → emit a `::warning::` annotation and a job-summary block explaining
  that the pipeline was skipped and nothing was published, then end **green**
  having installed nothing and done no work.
- **Key present** → run exactly as before, `--require-eia-key` still attached.

An empty secret is treated as absent, since a secret set to `""` is not a key.

## Rejected alternatives

**Leave it failing.** Rejected on the reading above. It also wastes ~3 minutes of
runner time to reach a conclusion the first step already knows.

**Drop `--require-eia-key` so the run succeeds against the fixture.** Rejected
absolutely. This is the failure mode the flag exists to prevent — it would commit
fixture-derived numbers to `metrics/` on a schedule, which is precisely the thing
[0001](0001-synthetic-fixture-instead-of-waiting.md) is built to make impossible.
The flag stays on the run step, because the preflight only covers "no secret at
all"; a secret that exists but is empty or rejected mid-run must still hard-fail.

**`continue-on-error: true` on the pipeline step.** Rejected: it turns the step
yellow but still runs the whole install-and-execute path to produce a failure
that is then ignored — and it would mask a *genuine* failure once a key exists,
which is far worse than a cosmetic red X now.

**Delete the workflow until the key arrives.** Rejected because the workflow is
part of what the project is demonstrating, and because the activation checklist
lives in its header comment. A missing file documents nothing.

## Consequences

- Someone who enables the `schedule:` block *without* configuring the key gets
  green runs that do nothing, forever. This is the real risk of the decision.
  Mitigated by the `::warning::` annotation and the job summary, both of which
  say plainly that the run was skipped and why — a green-with-warning run is
  visible without being alarming. It is a deliberate trade of "loud and wrong" for
  "quiet and accurate".
- Six steps now carry an `if:` guard, which is more to read.
- `tests/test_workflows.py` pins both halves: that every non-checkout step is
  gated, **and** that the dormant path never became a way to publish fixture
  numbers (`--require-eia-key` and `--source real` must both still be present,
  `--source synthetic` must not).

## What would reverse this

The key landing. Once `EIA_API_KEY` is a repository secret the preflight always
takes the `has_key=true` branch, and the guards become inert. They should be left
in place rather than removed — they are what makes the workflow safe to
re-run on a fork, where the secret will not exist.

If the project ever gains a second required secret, this preflight should become
a general "are the prerequisites present" check rather than growing a second
bespoke branch.
