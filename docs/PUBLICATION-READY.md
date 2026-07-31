# Publication readiness

*Assessed at commit `a7e45a2`, branch `main`, no remote configured.*

This document answers one question — **could a stranger clone this and reproduce
it?** — and then lists everything a reviewer is likely to trip on, including the
things that make the project look worse. A readiness note that only lists
strengths is a sales page, not an assessment.

---

## The short answer

**Yes, with one honest exception: the demand data.**

A stranger with `uv` and Node can clone this repo and, in about four minutes and
with no API key and no network, reproduce **every number it publishes, exactly**.
The fixture is seeded and date-anchored, so the metrics come out byte-identical —
this was verified by re-running the whole chain and diffing (`docs/REPRODUCE.md`
§4: only timestamps and registry versions moved; both PNGs were unchanged).

What they **cannot** reproduce is any statement about electricity demand, because
there isn't one. There is no EIA API key, so the demand series is synthetic and
every artifact says so. That is a gap in the *data*, not in the reproduction.

| | |
|---|---|
| **Reproduces exactly** | every MAE, MAPE, RMSE, bias, PSI, KS statistic, the retrain verdict, both PNGs, the full test suite, the lint result, the dashboard build |
| **Reproduces but differs in detail** | MLflow run ids and model versions (each run registers a new one), wall-clock timings, `generated_at_utc`, and the Open-Meteo row counts — that leg is live, so it genuinely moves |
| **Cannot be reproduced at all** | any real demand number, and any real drift episode |

### What a stranger actually needs

```bash
git clone <repo> && cd energy-forecast-drift
uv sync --extra dev                 # Python 3.11+, pinned in uv.lock
uv run pytest                       # ~16 s
uv run python -m pipeline.daily     # ~6 s, produces metrics/ + 2 PNGs
cd dashboard && npm ci && npm test && npm run build
```

- **No `.env` and no API key.** Every entrypoint degrades to the fixture with a
  loud warning. This is the normal path today, not a fallback for the impatient.
- **No network required.** `pipeline.daily` catches any ingestion exception and
  marks the stage `degraded` rather than failing (`pipeline/daily.py:239-243`),
  so an offline clone still scores the fixture end to end. With network, the
  Open-Meteo leg is real and runs.
- **No database, no server, no container.** MLflow is local sqlite; the dashboard
  is a static `dist/`.
- **Disk:** about 860 MB after a full setup — `.venv` ~741 MB, `node_modules`
  ~117 MB. Both gitignored. The clone itself is 1.5 MB.

Verified toolchain: Python 3.11.12, uv 0.6.17, Node v24.13.0, npm 9.8.1, on
Windows 11.

---

## Verified at this commit

| Check | Result |
|---|---|
| Python suite | **180 collected · 178 passed · 2 skipped · 0 failures · 0 errors** (16.4 s) |
| Dashboard suite | **4 passed / 1 file** |
| `ruff check .` | All checks passed — exit 0 |
| `ruff format --check .` | 59 files already formatted — exit 0 |
| `npm ci && npm run build` | exit 0 — `dist/` = 9 files, 885 KB |
| `pipeline.daily` | exit 0, six stages, verdict WATCH |
| `--require-eia-key` without a key | **exit 2, no directory created** |
| Every `metrics/*.json` | `is_real: false`, warning present, no `is_real: true` anywhere |
| README banner | in the **first 12 lines**, containing both "SYNTHETIC" and "benchmark" |
| Publication scan | `SAFE TO PUBLISH: yes` — worktree **and** all 149 blobs across all 25 commits |

Every `ci.yml` step was additionally executed locally against Windows paths, and
each behaved as the workflow requires — including the two that must *fail*: the
injected-shift alarm exited 1, and the no-key guard exited 2 writing nothing.

---

## Things a reviewer will trip on

Ordered by how likely they are to cause a raised eyebrow.

### 1. Every number is synthetic — and that is the headline

Unavoidable and deliberate, but it is the first thing a reviewer meets and it
will shape everything after it. The mitigation is that it is stated before any
number rather than discovered after one: a heading-sized banner in the README's
first 12 lines, `"is_real": false` in all six artifacts, watermarks on both PNGs,
a red `role="alert"` banner on the dashboard, and `tests/test_artifacts.py`
failing the build if any artifact ever claims otherwise.

**A reviewer may still conclude the project is unfinished.** It is — the data leg
is. What is on offer is the engineering, and the README's "if you are reviewing
this in five minutes" table points each claim at both the code that enforces it
and the test that proves it.

### 2. CI has never actually run

There is no remote, so **GitHub Actions has never executed a single workflow**.
The badge-shaped confidence a green check normally provides does not exist here.

Every *command* in `ci.yml` has been run locally and passes, and both YAML files
parse under `yaml.safe_load` (pinned by `tests/test_workflows.py`). What is
unexercised is the **runner plumbing**: the `/tmp/smoke` paths, `test -s`,
`set +e`, the bash heredoc in the artifact-provenance step, and `ubuntu-latest`
itself. This repo was built and verified entirely on Windows.

**Expect the first push to need a small CI fixup.** That is a normal cost of a
remote-less build, not a hidden defect, but it should not be a surprise.

### 3. The author's email is in the git history — including one blob that was meant to be masked

Every one of the 25 commits carries a personal Gmail address in the author and
committer fields, permanently public once the repo is.

Separately, blob `cf61e922e2` — the version of `docs/PUBLICATION-SCAN.md`
committed in `c1a7935` — contains that address *unmasked in the file body*,
because the first draft of the scan report printed the very thing it was written
to find. The worktree was fixed; the blob cannot be, without a history rewrite.

**No incremental exposure** (anyone who can read the blob can read `git log`), and
**no rewrite was performed** — that is Rodrigo's call. Full reasoning in
`PUBLICATION-SCAN.md` §A1 and §7/R4.

### 4. `docs/spec.md` is in Portuguese

Every other document is in English. A reviewer clicking through from the README's
"Full brief" link lands on Portuguese without warning. It is the original brief
and translating it would misrepresent it as something written for this audience,
but the link deserves a language note.

### 5. The publication scanners are not in the repo

`PUBLICATION-SCAN.md` describes two scripts under `reports/_scan/`, and
`reports/` is gitignored — so a reviewer cannot re-run the scan as written.
Deliberate (they are scaffolding, and one of them exists to find secrets, which
is not a published deliverable), and §6 of that report gives equivalent
one-liners. But the document does reference files that will not be there.

### 6. MLflow versions will not match the committed artifacts

Every `models.train` run registers a new model version. The committed artifacts
say champion `v4`; a fresh clone's first run will say `v1`. The *metrics* are
identical; the identifiers are not. Documented in `REPRODUCE.md` §8.

Related and now fixed: the artifacts had previously drifted to recording `v2`
while the local registry served `v3`, because `mlruns/` is gitignored and
`git checkout -- metrics/` cannot roll a registry back. All five now agree.

### 7. The drift verdict says WATCH with a red "Feature: Alert" chip

On the dashboard this reads at a glance as *something is wrong*. It is not — the
fixture carries a genuine annual cycle, so a 28-day reference window against a
14-day current window spans different months and the temperature and rolling
features really do move. That is precisely the case rule R4 exists for: a leading
indicator with no measured harm behind it, charted and not acted on.

A skimmer may read the red chip as a bug. The rationale is one line below it and
in the README, but the chip is louder than the sentence.

### 8. Smaller things

- **The Vite build prints a chunk-size warning** on every run (694 KB, 230 KB
  gzipped). ECharts is large and this is a single page with no routing, so
  code-splitting would buy nothing. Left visible rather than silenced.
- **Two tests skip.** Reported, not silent: `monitor.json` and `pipeline.json`
  carry no nested provenance block, so one cross-check has nothing to compare
  against. `-rs` prints the reason.
- **`dashboard/package.json` has no `engines` field.** Built and verified on Node
  24; older majors are untested.
- **The first `models.train` costs an extra ~40 s** creating `mlflow.db`.
- **`npm audit` reports 6 vulnerabilities** (4 moderate, 1 high, 1 critical) in
  the dev dependency tree — build tooling that never runs in production, since
  the output is a static `dist/`. Not triaged.
- **Running any verify command rewrites `metrics/`.** `models`, `models.train`,
  `drift.run` and `pipeline.daily` all do. A reviewer poking around will dirty
  their tree; `git checkout -- metrics/` restores it (but not the registry).
- **`--simulate-shift` writes into whatever `--out` it is given.** It stamps the
  artifact `simulated_shift`, so an injected demo can always be told from an
  observation — but pointed at `metrics/` it will overwrite the committed one.

---

## What is genuinely thin

Stated so a reviewer does not have to find it themselves.

1. **No evidence the model is any good.** A −14.8% MAE improvement over a
   seasonal naive on a synthetic curve is close to guaranteed and proves only
   that the two models were scored on identical folds. Nothing here demonstrates
   forecasting skill on real load.
2. **The drift loop has never caught real drift.** It has caught an injected
   shift of a size chosen by the person injecting it. The mechanism is tested in
   both directions; the phenomenon has not been observed.
3. **No production traffic, no deployment, no operational history.** `/forecast`
   has been exercised over local HTTP, not under load, not behind auth, not for
   any length of time. There is no deploy step in this repo by design.
4. **Single-author, single-machine, no external review.** Nothing here has been
   run by anyone else, on any other OS, or on a CI runner — see trip hazard 2.

---

## Verdict

**Publication-ready.** Nothing in the list above is a defect that should hold the
repo back; items 1–4 under *thin* are consequences of the missing API key, and
the rest are disclosure items rather than problems.

Two decisions remain, both Rodrigo's, neither blocking:

1. **The email in commit metadata** (and the one historical blob) — accept,
   switch to a GitHub noreply for future commits, or rewrite history. **An agent
   may not rewrite history**; it would change every SHA quoted across these docs.
2. **Whether to publish at all while the data is synthetic.** The case for yes:
   the engineering is the exhibit, it is complete, and it is honest about what it
   is. The case for waiting: a reviewer who reads only the README banner may not
   get as far as the engineering.

**No remote was created and nothing was pushed.** Creating the public repository
is a human action, by design.
