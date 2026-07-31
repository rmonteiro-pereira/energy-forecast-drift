# M4 — drift report

> ⚠️ **SYNTHETIC — NOT REAL DATA.** These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. They are a smoke test of the pipeline, NOT a benchmark. The real baseline is pending the EIA API key — see docs/BLOCKED.md.

- generated: `2026-07-31T01:45:10+00:00`
- source: `synthetic_fixture`
- reference: `2026-06-16T00:00:00+00:00` → `2026-07-14T00:00:00+00:00` (2,688 rows)
- current: `2026-07-14T00:00:00+00:00` → `2026-07-28T00:00:00+00:00` (1,312 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 8/14 feature(s) above PSI 0.2; worst is demand_roll_min_24h at PSI 6.655 |
| target | 🟢 ok | actual demand PSI 0.022, mean moved -133 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.027, mean moved -244 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,324 -> 2,534 MWh (+9.0%), MAPE +0.27 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_min_24h` | 6.6554 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 5.4174 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.0757 | 0.00e+00 | alert |
| `demand_roll_max_24h` | 2.4614 | 0.00e+00 | alert |
| `temp_last_1h` | 1.4542 | 0.00e+00 | alert |
| `temp_lag_168h` | 1.2934 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.4028 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.3184 | 0.00e+00 | alert |
