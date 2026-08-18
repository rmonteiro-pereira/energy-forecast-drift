# M4 — drift report

- generated: `2026-08-18T07:07:27+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-18T06:00:00+00:00` (1,516 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature, target drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 19/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.364 |
| target | 🔴 alert | actual demand PSI 0.485, mean moved +6,631 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.102, mean moved +3,314 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,386 MWh (+19.2%), MAPE +0.34 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.3643 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.4778 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 5.6281 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 5.0035 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.3748 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 2.8627 | 0.00e+00 | alert |
| `temp_last_1h` | 1.7871 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 1.7624 | 0.00e+00 | alert |
