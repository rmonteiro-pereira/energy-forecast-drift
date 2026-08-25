# M4 — drift report

- generated: `2026-08-25T07:10:54+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-25T06:00:00+00:00` (2,188 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 18/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.758 |
| target | 🟡 warn | actual demand PSI 0.137, mean moved +4,465 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.039, mean moved +1,396 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,148 MWh (+10.9%), MAPE +0.17 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7575 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.5256 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.7415 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.2343 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 1.2207 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.7563 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.7496 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.6662 | 0.00e+00 | alert |
