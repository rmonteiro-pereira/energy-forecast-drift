# Security Policy

## Reporting a vulnerability

Please report security issues **privately** rather than opening a public issue.

- Use GitHub's [private vulnerability reporting](https://github.com/rmonteiro-pereira/energy-forecast-drift/security/advisories/new) — preferred.
- Or email **rmonteiropereira1@gmail.com** with `SECURITY` in the subject.

Include the commit, the command you ran, and what you observed. Expect an acknowledgement
within **7 days**; this is a personal project, so treat that as best effort.

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
  failure.
- **Temporal leakage** in the feature builder or the backtest split. Leakage is blocked in
  several independent places and asserted by tests; a route around them is a finding.
- **Model deserialisation** — loading an untrusted artifact from the MLflow registry.
- **The serving layer** (`/forecast`) — unvalidated input reaching the model or the
  filesystem.
- **Dependency vulnerabilities** reachable from the CLI or the API.

## Out of scope

- Availability or accuracy of the upstream EIA and Open-Meteo services.
- The synthetic fixture producing unrealistic values — it is labelled synthetic everywhere by
  design.
- Resource exhaustion from deliberately configuring an extreme local backtest.

## A note on the numbers

Until a real EIA key is configured, **every metric in this repository is generated from a
seeded synthetic fixture** and is marked `"is_real": false`. That is a stated limitation, not
a vulnerability — but a bug that *hides* it is.
