# Security policy

## Reporting a vulnerability

Report privately through **[GitHub Security Advisories](https://github.com/rmonteiro-pereira/energy-forecast-drift/security/advisories/new)**
rather than opening a public issue. Please include what you found, how to
reproduce it, and what you think the impact is.

This is a portfolio project maintained by one person, not a product with an
on-call rota. Expect a first response within about a week. There is no bounty.

## Scope

| In scope | Out of scope |
|---|---|
| Secret handling and the redaction layer (`ingest/http.py`) | The public EIA and Open-Meteo APIs themselves |
| The `/forecast`, `/model`, `/health` endpoints in `serving/` | Dependency CVEs with no exploit path here — please still report, but they are unlikely to be urgent |
| Anything that could cause a credential to be written to a log, an artifact, or a commit | The synthetic fixture producing implausible numbers (that is documented, not a vulnerability) |
| The GitHub Actions workflows, particularly anything that could exfiltrate `EIA_API_KEY` | Denial of service against a local dev server |

## How secrets are handled

There is exactly one secret in this project: `EIA_API_KEY`, a free key from
[eia.gov/opendata](https://www.eia.gov/opendata/register.php). It grants read
access to public energy statistics. It is not a credential to anything private,
and it carries a rate limit rather than a bill.

That said, it is treated as a real secret throughout:

- **It lives in `.env` only**, which is gitignored (`.gitignore:2`). `.env` has
  never been tracked in any commit — verified in
  [`docs/PUBLICATION-SCAN.md`](docs/PUBLICATION-SCAN.md) §1.6.
- **It is never logged.** All HTTP goes through `ingest/http.py`, which defines
  `SECRET_PARAMS = {"api_key", "apikey", "token", "key"}` and scrubs them from
  URLs and parameter dicts before anything reaches a log line or an exception
  message. `tests/test_clients.py::test_secrets_never_survive_redaction` is the
  test that holds this in place.
- **A rejected key is never retried.** A 401 or 403 raises immediately instead of
  burning the rate limit on an attempt that cannot succeed.
- **In CI it is a repository secret**, referenced as `${{ secrets.EIA_API_KEY }}`
  and never echoed. `ci.yml` sets it to the empty string deliberately, so the
  test suite exercises the no-key path.
- **The daily workflow refuses to publish without it.** `--require-eia-key`
  makes `pipeline.daily` exit before writing anything, so a missing key can
  never result in fixture numbers being committed as though they were real.

If you believe a key has been exposed, revoke it at
[eia.gov/opendata](https://www.eia.gov/opendata/) and open an advisory. Because
the key is free and read-only, rotation costs nothing.

## What has already been checked

Before this repository was made public, the whole worktree **and every blob in
the full git history** were scanned for credentials, tokens, private addresses,
internal hostnames and absolute local paths. The report, including the findings
that were dismissed and why, is in
[`docs/PUBLICATION-SCAN.md`](docs/PUBLICATION-SCAN.md).

Two things that scan will always flag, and should not be reported as
vulnerabilities:

- `tests/test_clients.py` contains the literal string `SUPERSECRET`. It is the
  fixture in the test that proves redaction works. Removing it would remove the
  test.
- `docs/PUBLICATION-SCAN.md` quotes its own findings, so it contains the strings
  it reports. Redacting a report's evidence would make it unreviewable.

## Supply chain

- Python dependencies are pinned in `uv.lock`; JavaScript in
  `dashboard/package-lock.json`. Both are committed.
- CI installs with `uv sync --frozen`, so a lockfile drift fails the build rather
  than silently resolving something new.
- `npm audit` currently reports advisories in the dashboard's **dev** dependency
  tree (build tooling). The published output is a static `dist/` with no runtime
  npm dependencies, so those advisories have no execution path in anything this
  project ships. They are not triaged individually; if you find one that *does*
  have a path, that is in scope and worth reporting.

## Not a security issue

**Every number this repository publishes is synthetic**, computed from a seeded
fixture, and every artifact says so via `"is_real": false`. That is the
documented state of the project, enforced by `tests/test_artifacts.py`, and it is
described at length in the README. It is not a vulnerability — but if you find a
path by which a synthetic artifact could be published *claiming* to be real, that
very much is, and I would like to know.
