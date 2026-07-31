# Security Policy

## Reporting a vulnerability

Please report security issues **privately** rather than opening a public issue.

- Use GitHub's [private vulnerability reporting](https://github.com/rmonteiro-pereira/energy-forecast-drift/security/advisories/new) — preferred.
- Or email **rmonteiropereira1@gmail.com** with `SECURITY` in the subject.

Include the commit, the command you ran, and what you observed. Expect an acknowledgement
within **7 days**; this is a personal project, not a product with an on-call rota, so treat
that as best effort. There is no bounty.

## What this project handles

A forecasting and drift-monitoring pipeline over **public** energy demand and weather data.
It holds no personal data.

**No credentials belong in this repository.** The EIA API key is read from the environment
(`EIA_API_KEY`) and must never be committed. Open-Meteo needs no key. If you find anything
credential-shaped committed, report it privately rather than opening an issue.

## Areas worth reporting

- **A path that flips `is_real` without real data behind it.** Every artifact carries an
  `is_real` flag, the plots are watermarked, MLflow runs are tagged, and `/forecast` checks
  the flag before answering. Anything that lets a synthetic result be presented as real is
  the most serious class of bug in this repository — it is a correctness *and* an honesty
  failure. `tests/test_artifacts.py` is the guard; a route around it is a finding.
- **Temporal leakage** in the feature builder or the backtest split. Leakage is blocked in
  several independent places and asserted by tests; a route around them is a finding.
- **Model deserialisation** — loading an untrusted artifact from the MLflow registry.
- **The serving layer** (`/forecast`) — unvalidated input reaching the model or the
  filesystem.
- **Anything that could write a credential** to a log, an artifact, or a commit.
- **The GitHub Actions workflows**, particularly anything that could exfiltrate
  `EIA_API_KEY`.
- **Dependency vulnerabilities** reachable from the CLI or the API.

## Out of scope

- Availability or accuracy of the upstream EIA and Open-Meteo services.
- The synthetic fixture producing unrealistic values — it is labelled synthetic everywhere by
  design.
- Resource exhaustion from deliberately configuring an extreme local backtest.
- Denial of service against a local dev server.
- Dependency CVEs with no exploit path here. Please still report them; they are just
  unlikely to be urgent.

## How the one secret is handled

There is exactly one secret in this project: `EIA_API_KEY`, a free key from
[eia.gov/opendata](https://www.eia.gov/opendata/register.php). It grants read access to
public energy statistics — it is not a credential to anything private, and it carries a rate
limit rather than a bill. It is still treated as a real secret throughout:

- **Two homes, no others:** `.env` for local development (gitignored at `.gitignore:2`) and a
  GitHub Actions repository secret for CI, referenced only as `${{ secrets.EIA_API_KEY }}`.
  `.env` has never been tracked in any commit — verified in
  [`docs/PUBLICATION-SCAN.md`](docs/PUBLICATION-SCAN.md) §1.6.
- **Never logged.** All HTTP goes through `ingest/http.py`, which defines
  `SECRET_PARAMS = {"api_key", "apikey", "token", "key"}` and scrubs them from URLs and
  parameter dicts before anything reaches a log line or an exception message.
  `tests/test_clients.py::test_secrets_never_survive_redaction` holds this in place.
- **A rejected key is never retried.** A 401 or 403 raises immediately instead of burning the
  rate limit on an attempt that cannot succeed.
- **CI deliberately runs without it.** `ci.yml` sets `EIA_API_KEY: ""` so the test suite
  exercises the no-key path on every run.
- **The daily workflow refuses to publish without it.** `--require-eia-key` makes
  `pipeline.daily` exit before writing anything, so a missing key can never result in fixture
  numbers being committed as though they were real.

If you believe a key has been exposed, revoke it at
[eia.gov/opendata](https://www.eia.gov/opendata/) and open an advisory. Because the key is
free and read-only, rotation costs nothing.

## What has already been checked

Before this repository was made public, the whole worktree **and every blob in the full git
history** were scanned for credentials, tokens, private addresses, internal hostnames and
absolute local paths. The report — including the findings that were dismissed, and why — is
[`docs/PUBLICATION-SCAN.md`](docs/PUBLICATION-SCAN.md).

Two things that scan will always flag, and which should **not** be reported as
vulnerabilities:

- `tests/test_clients.py` contains the literal string `SUPERSECRET`. It is the fixture in the
  test that proves redaction works. Removing it would remove the test.
- `docs/PUBLICATION-SCAN.md` quotes its own findings, so it contains the strings it reports.
  Redacting a report's evidence would make it unreviewable.

## Supply chain

- Python dependencies are pinned in `uv.lock`; JavaScript in `dashboard/package-lock.json`.
  Both are committed.
- CI installs with `uv sync --frozen`, so lockfile drift fails the build rather than silently
  resolving something new.
- Dependabot raises grouped monthly updates for uv, npm and GitHub Actions
  (`.github/dependabot.yml`). Security advisories from GitHub are surfaced immediately,
  independent of that schedule.
- `npm audit` currently reports advisories in the dashboard's **dev** dependency tree (build
  tooling). The published output is a static `dist/` with no runtime npm dependencies, so
  those advisories have no execution path in anything this project ships. They are not
  triaged individually; if you find one that *does* have a path, that is in scope.

## A note on the numbers

Until a real EIA key is configured, **every metric in this repository is generated from a
seeded synthetic fixture** and is marked `"is_real": false`. That is a stated limitation, not
a vulnerability — but a bug that *hides* it is the most serious thing you could find here.
