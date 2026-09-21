# M4 — drift report

- generated: `2026-09-21T12:54:54+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-21T12:00:00+00:00` (4,804 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.448 |
| target | 🟡 warn | actual demand PSI 0.047, mean moved +1,910 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.033, mean moved -1,064 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,505 MWh (+23.4%), MAPE +0.57 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.4476 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.5533 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8476 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5994 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4641 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.3968 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.3497 | 0.00e+00 | alert |
| `wind_fcst_target` | 0.2780 | 0.00e+00 | alert |
