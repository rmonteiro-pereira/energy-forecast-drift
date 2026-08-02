# Publication safety scan

**Repository:** `energy-forecast-drift`
**Scanned:** at commit `5a9c5f6`, branch `main`, **no git remote configured**
**Re-scanned:** at the tip after the publication work landed — see [§7](#7-the-scan-run-against-its-own-report),
which is where the re-scan caught a leak in *this file*
**Scope, as scanned:** the entire worktree (tracked *and* untracked) plus **every blob on
every ref in the full history** — 125 distinct blobs across 21 commits.

Run before the repository was made public. Everything below is the real output of the
commands shown; nothing is summarised from memory. **Every candidate secret is masked** —
this document itself is going public, so it must not become the leak it is looking for.

> **This is a pre-flight record with a date on it, not a standing guarantee.** The
> repository has moved since. As of 2026-08-01, what a plain `git clone` gets — `main` —
> is **236 distinct blobs across 36 commits**:
>
> ```bash
> git rev-list --objects main | cut -d' ' -f1 | sort -u \
>   | git cat-file --batch-check='%(objecttype)' | sort | uniq -c
> #   236 blob   126 tree    36 commit
> ```
>
> The scan above covered 125 blobs across 21 commits, on every ref rather than on `main`
> alone. It has **not** been re-run over the difference, and this document does not claim
> it has. What the difference consists of is documentation edits, the dashboard dependency
> bumps Dependabot opened, and the mutation-testing work — no data files and no new
> credentials-shaped surface — but "I know what those commits are" is a weaker claim than
> "I scanned them", and it is stated as the weaker one.
>
> Its verdict for the history it covers stands, and that history is an ancestor of today's:
> nothing below has been invalidated, only outrun. **Re-run the commands in §1–§6 before
> treating the verdict as current.**

---

## VERDICT

```
SAFE TO PUBLISH: yes
```

No secret, key, token, credential, private address or internal hostname was found in the
worktree or anywhere in the git history. Nothing over 5 MB has ever been committed. No
`mlruns/`, `*.db`, parquet, `data/`, `node_modules/` or `dist/` path has ever entered a
commit.

Two items are **advisory, not blocking** — they are Rodrigo's call, and the repository is
publishable either way:

1. **The commit author email is a personal Gmail address** and will be permanently public
   in the commit metadata of all 21 commits. See [A1](#a1--author-email-is-public).
2. **`docs/BLOCKED.md` and the README describe an unfinished project.** That is deliberate
   and correct, but a reviewer skimming will meet it early. See [A2](#a2--the-repo-advertises-its-own-gap).

**No git history rewrite is required, and none was performed.** History is clean as it
stands. Had a rewrite been needed it would have been escalated rather than done — see
`_openwiki/program/blockers.md`.

---

## 1. Secrets

### 1.1 Method

A single scanner runs over two scopes: the worktree (all files, tracked and untracked,
skipping `.git`, `node_modules`, `.venv`, `dist`, `data`, `mlruns`, `reports`, and binary
suffixes), and the full history (`git rev-list --objects --all` → every blob, including
blobs unreachable from `HEAD`). Fifteen patterns: EIA-key shape (40 alphanumeric chars),
AWS access keys, GitHub / Slack / Google / OpenAI tokens, PEM private-key blocks, JWTs,
`name = value` assignments to secret-looking names, hardcoded bearer credentials, RFC1918
addresses, internal hostname suffixes (`.internal .corp .intranet .lan .local`), absolute
Windows user paths, absolute project paths, and email addresses.

```
$ .venv/Scripts/python.exe reports/_scan/scan_secrets.py worktree
$ .venv/Scripts/python.exe reports/_scan/scan_secrets.py history
```

The scanner lives under `reports/`, which is gitignored, so the scanner is not itself
published.

### 1.2 Worktree — full output

```
# scanned 90 worktree files (incl. untracked, excl. ['.git', '.pytest_cache', '.ruff_cache',
  '.venv', '__pycache__', 'data', 'dist', 'mlartifacts', 'mlruns', 'node_modules',
  'reports', 'venv'])

## eia-key-shape  (4 hits, 4 without a benign marker)
   why: EIA v2 API keys are 40 alphanumeric chars
   [REVIEW] dashboard/package-lock.json:386  value=wcBC************************awA7  (len=40)
            | "integrity": "sha512-5JcRxxRDUJLX8JXp/wcBCy3pENnCgBR9bN6JsY4Omhf...
   [REVIEW] dashboard/package-lock.json:891  value=995u************************O4mF  (len=40)
            | "integrity": "sha512-XLFHnR3tXMjbOCh2vtVJHmxt+995uJsTERQyseFDRA0...
   [REVIEW] dashboard/package-lock.json:969  value=ldwe************************9M2K  (len=40)
            | "integrity": "sha512-+2Cy/ldweGBLlPIKsQLF8U5N44a0KDdbrk1rAjHOM9M...
   [REVIEW] dashboard/package-lock.json:1556 value=jP4y************************209w  (len=40)
            | "integrity": "sha512-Js0m9cx+qOgDxo0eMiFGEueWztz+d4+M3rGlmKPT+T4...

## assigned-secret  (1 hits, 1 without a benign marker)
   why: a secret-looking name assigned a literal value
   [REVIEW] tests/test_clients.py:194  value=SUPE********************urly  (len=28)
            | url = "https://api.eia.gov/v2/x/data/?api_key=SUPERSECRET&frequency=hourly"
```

That is the complete output. **Eleven of the fifteen patterns matched nothing at all** —
including every real credential format, every private address, every internal hostname,
every absolute local path, and every email address.

### 1.3 History — full output

```
# scanned 125 distinct blobs across ALL refs and history

## eia-key-shape  (4 hits, 4 without a benign marker)
   [REVIEW] 42ae55ebc3 dashboard/package-lock.json:386   value=wcBC****...****awA7  (len=40)
   [REVIEW] 42ae55ebc3 dashboard/package-lock.json:891   value=995u****...****O4mF  (len=40)
   [REVIEW] 42ae55ebc3 dashboard/package-lock.json:969   value=ldwe****...****9M2K  (len=40)
   [REVIEW] 42ae55ebc3 dashboard/package-lock.json:1556  value=jP4y****...****209w  (len=40)

## assigned-secret  (1 hits, 1 without a benign marker)
   [REVIEW] 1217fc2cc4 tests/test_clients.py:194  value=SUPE****...****urly  (len=28)
```

**The history findings are identical to the worktree findings.** That is the important
result: it means no secret was ever committed and later deleted. There is nothing hiding in
an old commit that a `git checkout` would resurrect.

### 1.4 Adjudication of every hit

| # | File:line | Pattern | Verdict |
|---|---|---|---|
| S1 | `dashboard/package-lock.json:386, 891, 969, 1556` | `eia-key-shape` | **False positive.** These are npm Subresource-Integrity digests — `sha512-…` base64. The regex found 40-char alphanumeric *substrings inside* them. They are published checksums of public npm tarballs, by design. Not secrets. |
| S2 | `tests/test_clients.py:194` | `assigned-secret` | **False positive, and load-bearing.** The literal is the string `SUPERSECRET` inside `test_secrets_never_survive_redaction`, which asserts that `http.redact()` strips it: `assert "SUPERSECRET" not in http.redact(url)`. Deleting it would remove the test that proves keys are scrubbed from logs. Keep it. |

### 1.5 Where the key actually lives

`git grep -n -I -E 'EIA_API_KEY' -- . ':(exclude)uv.lock'` — 26 hits, and **every one is a
read, a message, or a placeholder.** No hit is an assignment of a real value:

| Kind | Sites |
|---|---|
| Read from the environment | `ingest/config.py:105` (`os.getenv`) |
| Error / instruction text naming the variable | `ingest/eia.py:48`, `ingest/http.py:67`, `ingest/__main__.py:69-71`, `models/data.py:58`, `pipeline/daily.py:73-78,112` |
| Empty placeholder in the committed template | `.env.example:6` → `EIA_API_KEY=` (no value) |
| GitHub Actions secret reference | `.github/workflows/daily.yml:93` → `${{ secrets.EIA_API_KEY }}` |
| Deliberately blanked in CI | `.github/workflows/ci.yml:85` → `EIA_API_KEY: ""` |
| Test placeholders | `tests/test_clients.py` → `"test-key"`; `tests/test_pipeline_daily.py:137` deletes the var |

### 1.6 The `.env` file

```
$ git log --all --name-only --format= | sort -u | grep -iE '(^|/)\.env'
.env.example

$ ls -la .env
cannot access '.env': No such file or directory

$ git check-ignore -v .env
.gitignore:2:.env	.env
```

`.env` has **never** been tracked in any commit, does not exist on this machine, and is
ignored by `.gitignore:2`. Only `.env.example` is committed, and its `EIA_API_KEY=` is
empty.

### 1.7 Redaction is enforced in code, not by convention

`ingest/http.py:26` declares `SECRET_PARAMS = {"api_key", "apikey", "token", "key"}`, and
`redact()` / `redact_params()` (lines 29 and 35) scrub those before anything reaches a log
line or an exception message. `tests/test_clients.py:193` is the test that holds it in
place. This is why an unattended daily cron can safely log its own request URLs.

---

## 2. Size and weight

```
$ .venv/Scripts/python.exe reports/_scan/scan_size.py
```

### 2.1 Full history

```
## Largest blobs in the FULL history (all refs, all commits)
   125 distinct blobs
   blobs > 5 MB: 0
       802.8 KB  348324dcf1  uv.lock
       802.4 KB  b58e8bb0b1  uv.lock
       613.3 KB  77e749369a  uv.lock
       321.6 KB  e68e8f337b  metrics/forecast_vs_actual.png
        89.1 KB  bf76927a70  metrics/forecast.json
        89.1 KB  721049c4fe  metrics/forecast.json
        80.9 KB  57a64f81d7  uv.lock
        75.9 KB  71db70e418  metrics/rolling_mae.png
        64.1 KB  c77e7f515f  metrics/drift.json
        55.6 KB  42ae55ebc3  dashboard/package-lock.json
        52.0 KB  2187a1c5e0  metrics/drift.json
        51.5 KB  b366a55f8f  metrics/drift.json

   sum of all distinct blob bytes: 3.7 MB

## .git directory on disk: 1.5 MB
```

**Zero blobs over 5 MB, in any commit, on any ref.** The largest object ever committed is
an 803 KB `uv.lock`. The whole history is 3.7 MB of distinct blob content and packs to a
1.5 MB `.git`. This clones instantly.

### 2.2 Worktree

```
## Largest TRACKED files in the worktree (92 files)
       802.8 KB  uv.lock
       321.6 KB  metrics/forecast_vs_actual.png
        92.7 KB  metrics/forecast.json
        75.9 KB  metrics/rolling_mae.png
        66.3 KB  metrics/drift.json
        55.6 KB  dashboard/package-lock.json
        29.0 KB  README.md
        26.5 KB  pipeline/daily.py
        19.6 KB  drift/detectors.py
        18.3 KB  metrics/model.json
        16.2 KB  docs/writeup.md
        15.1 KB  models/train.py

   total tracked bytes: 1.8 MB
```

### 2.3 Forbidden classes

```
## Forbidden classes -- tracked right now?
    clean  mlruns/              0 tracked
    clean  mlartifacts/         0 tracked
    clean  data/                0 tracked
    clean  reports/             0 tracked
    clean  *.db / *.sqlite*     0 tracked
    clean  *.parquet            0 tracked
    clean  node_modules/        0 tracked
    clean  dashboard/dist/      0 tracked
    clean  .env (real)          0 tracked

## Forbidden classes -- ever committed in ANY past commit?
    clean  mlruns/              0 paths
    clean  data/                0 paths
    clean  *.db / *.sqlite*     0 paths
    clean  *.parquet            0 paths
    clean  node_modules/        0 paths
    clean  dashboard/dist/      0 paths
    clean  .env (real)          0 paths
```

Clean in both scopes. Nothing was committed and later removed.

### 2.4 The heavy directories are present but ignored

```
## Heavy directories on disk that MUST stay ignored
         4.7 MB  mlruns                  ignored=True
         absent  mlartifacts
        16.7 KB  data                    ignored=True
         4.7 MB  reports                 ignored=True
       884.7 KB  dashboard/dist          ignored=True
       117.3 MB  dashboard/node_modules  ignored=True
       741.4 MB  .venv                   ignored=True
```

868 MB sits in the working directory and **none of it is tracked.** `reports/` is 4.7 MB
because that is where the Evidently HTML report is written — inlined Plotly, deliberately
routed out of `metrics/` for exactly this reason.

### 2.5 Committed images

```
## Committed images
       321.6 KB  metrics/forecast_vs_actual.png
        75.9 KB  metrics/rolling_mae.png
```

Two PNGs, 397 KB total. Both are regenerated by `python -m pipeline.daily`, and
`pipeline/plots.py::_stamp_if_synthetic` draws a rotated
`SYNTHETIC FIXTURE — NOT REAL DATA` watermark across them whenever `is_real` is
false — which it was at the time of this scan, and which is why the watermark was
visible in the copies committed then.

*Updated 2026-08-01: it no longer is.* The key landed, the daily pipeline ran
against real PJM demand, and the regenerated PNGs carry `is_real: true` and
therefore no stamp. The mechanism is unchanged; the absence of the watermark is
now itself the provenance signal.

---

## 3. Advisory findings

### A1 — Author email is public

```
$ git log --all --format='%ae|%an|%ce|%cn' | sort -u
rodr*********************@gmail.com|Rodrigo Monteiro Pereira|rodr*********************@gmail.com|Rodrigo Monteiro Pereira
```

*(Masked, like every other value in this report. An earlier draft printed it in
full — the re-scan at the final commit caught that, which is written up in
[§7](#7-the-scan-run-against-its-own-report).)*

Every commit carries a personal Gmail address in both the author and committer fields. Once
the repository is public this is permanently readable and scrapeable — and unlike a file,
commit metadata cannot be corrected without rewriting history.

**This is normal and many people publish this way.** It is flagged because it is a
deliberate choice, not because it is a defect. If Rodrigo would rather not publish it, the
options are:

- Accept it. For a portfolio repo shown to a named recruiter, a real address is arguably a
  feature.
- Set `git config user.email <id>+<user>@users.noreply.github.com` for **future** commits
  only. Cheap, no rewrite, but the existing 21 commits keep the Gmail address.
- Rewrite the 21 commits' author/committer fields. **Not done here, and not recommended
  unilaterally** — it changes every SHA in this document and in `state.md`, and the brief
  reserves history rewrites for Rodrigo. Escalated in `_openwiki/program/blockers.md`.

**No action taken.**

### A2 — The repo advertises its own gap

`docs/BLOCKED.md` states plainly that the project's central variable — real PJM demand —
is unavailable, and the README leads with a banner saying no number in the repo is a
benchmark. A reviewer meets this within seconds.

This is **intended and is the correct call**, so it is recorded as an advisory rather than
a fix. The alternative — quietly shipping synthetic numbers that read as results — is the
failure mode this whole apparatus exists to prevent. Phase PUB4-2 leans into it: the
README is reframed so the *engineering* is the exhibit and the fixture is stated up front
rather than discovered.

**No action taken beyond the PUB4-2 reframing.**

---

## 4. What was checked and found nothing

Recorded so the negative results are not mistaken for gaps in the scan.

| Check | Result |
|---|---|
| AWS access keys (`AKIA…`, `ASIA…`) | 0 hits, worktree and history |
| GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`) | 0 hits |
| Slack tokens (`xoxb-`, `xoxp-`, …) | 0 hits |
| Google API keys (`AIza…`) | 0 hits |
| OpenAI-style keys (`sk-…`) | 0 hits |
| PEM private-key blocks | 0 hits |
| JWTs | 0 hits |
| Hardcoded `Bearer …` credentials | 0 hits |
| RFC1918 private addresses (10/8, 192.168/16, 172.16/12) | 0 hits |
| Internal hostnames (`.internal .corp .intranet .lan .local`) | 0 hits |
| Absolute Windows user paths (`C:\Users\…`) | 0 hits — **still 0 at the final commit** |
| Absolute project paths (`E:\Projetos…`) | 0 hits at this run; see [§7](#7-the-scan-run-against-its-own-report) — the documents written *after* this scan introduced some, and they were removed |
| Email addresses in file contents | 0 hits at this run; see [§7](#7-the-scan-run-against-its-own-report) — this report itself later introduced one, and it is now masked |
| A real `.env` in any commit | never tracked |
| Blobs > 5 MB in history | 0 |
| `mlruns/`, `*.db`, parquet, `data/`, `node_modules/`, `dist/` in history | 0 |
| Git remotes configured | none |

The absence of any absolute Windows **user** path means the repo carries no trace of the
account it was built on — no `C:\Users\<name>` in any tracked file, at any commit.

---

## 5. Remediation

None required. `SAFE TO PUBLISH: yes`.

The two advisory items (A1, A2) are decisions for Rodrigo, not defects, and neither blocks
publication. Both are recorded in `_openwiki/program/blockers.md` so they are not lost.

## 6. Reproducing this scan

Both scanners live in `reports/_scan/`, which is gitignored and therefore **not** part of
the published repository — they are scaffolding, not a deliverable. To re-run before
publishing, recreate them or use the equivalent one-liners:

```bash
# every blob on every ref, largest first
git rev-list --objects --all \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" {print $3, $4}' | sort -rn | head -20

# forbidden paths, ever
git log --all --name-only --format= | sort -u \
  | grep -E '^(mlruns|mlartifacts|data)/|\.(db|sqlite3?|parquet)$|node_modules/|^dashboard/dist'

# the key, everywhere it is named
git grep -n -I -E 'EIA_API_KEY' -- . ':(exclude)uv.lock'
```

---

## 7. The scan run against its own report

The scan above ran at commit `5a9c5f6`. Three commits of publication work landed
after it, so it was re-run against the final tree — and it immediately flagged
**the documents the publication work had just written**. Recorded here rather than
quietly fixed, because a scanner that exempts its own output is not a scanner.

| # | Where | Pattern | What happened |
|---|---|---|---|
| R1 | `docs/PUBLICATION-SCAN.md` §A1 | `email` | **This report printed the author's Gmail address in full**, in the block demonstrating that the address is exposed — while its own opening paragraph promised every value would be masked. Genuine defect. **Fixed:** the address is now masked like every other value. |
| R2 | `docs/REPRODUCE.md` | `abs-project-path` | The pasted `pytest` and `vitest` headers carried the absolute path of the machine they ran on. Low severity — it leaks a directory layout, not a username or a credential — but it is the exact category §4 claims is at zero. **Fixed:** shortened to `<repo>`, with the edit declared at the top of that document. |
| R3 | `docs/PUBLICATION-SCAN.md` §1.2 | `assigned-secret`, `abs-project-path` | This report quotes the scanner's own output, so it necessarily contains the strings the scanner matches — `SUPERSECRET`, `E:\Projetos…` inside the "0 hits" table row. **Not fixed, by design.** These are quotations of findings, and redacting a report's evidence would make it unreviewable. A re-run will always flag this file; that is the correct behaviour and this row is the explanation. |
| R4 | git history, blobs `cf61e922e2` and `93f995b401` | `email`, `abs-project-path` | The R1 and R2 fixes corrected the working files. **They did not, and could not, correct the committed blobs.** Detailed below. |

Nothing in R1–R4 was a credential. No key, token, or password appeared at any
point, in any scope. But R1 is worth stating plainly: **the first version of this
document leaked one of the two things it was written to find.** The re-scan caught
it in the worktree before publication — and R4 is the honest footnote that
catching it there was not the same as removing it. That is the entire argument
for scanning history separately from the worktree, and for scanning again at the
end rather than only at the start.

### R4 — fixing a file does not unfix the history

The R1 fix corrected the **worktree**. It could not correct the **history**, and
saying otherwise would be the exact error this report exists to avoid.

```
$ python reports/_scan/scan_secrets.py history

# scanned 149 distinct blobs across ALL refs and history
## email  (2 hits)
   [REVIEW] cf61e922e2 docs/PUBLICATION-SCAN.md:272  value=rodr***********************.com  (len=33)
```

Blob `cf61e922e2` is the version of **this file** committed in `c1a7935`, before
the mask was applied. It is unreachable from `HEAD`'s content but perfectly
readable via `git show c1a7935:docs/PUBLICATION-SCAN.md`. The same is true of
`93f995b401` — the pre-fix `docs/REPRODUCE.md` with its absolute local paths.

**Assessment: no incremental exposure, and therefore not a blocker.** The address
is already in the author *and* committer fields of every one of the 25 commits
(finding [A1](#a1--author-email-is-public)). Anyone who can read that blob can
run `git log --format=%ae` and get the same string in less time. Removing the
blob would leave the metadata, so it would buy nothing without also rewriting
every commit — which is [A1](#a1--author-email-is-public)'s decision, is
explicitly reserved for Rodrigo, and **was not done**.

If Rodrigo does decide to scrub the address, the two must be done together:
rewriting author/committer identities *and* the two blobs, in one pass, accepting
that every SHA quoted in these documents changes. Half of that job is worse than
none of it.

---

## Final verdict

Both scopes, at the tip:

| Scope | Extent | Credentials found |
|---|---|---|
| **Worktree** | 95 files, tracked **and** untracked | **0** |
| **Full history** | **149 distinct blobs across every ref and all 25 commits** — not just `HEAD`, and including blobs unreachable from it | **0** |

Everything the scanner still matches, in either scope, is accounted for:

- the four npm `sha512-` integrity digests in `dashboard/package-lock.json` (S1) —
  published checksums of public tarballs;
- the `SUPERSECRET` literal in `tests/test_clients.py` (S2) — the fixture in the
  test that proves `http.redact()` scrubs keys, plus this report's quotation of it;
- this report's own quotations of its findings (R3);
- the two pre-fix blobs described in R4 — cosmetic, and strictly dominated by the
  commit metadata in A1.

**No API key, token, password, private key, JWT, RFC1918 address, internal
hostname or `C:\Users\…` path exists in the worktree or in any commit. No blob
over 5 MB has ever been committed. `.env` has never been tracked. No git history
was rewritten.**

```
SAFE TO PUBLISH: yes
```
