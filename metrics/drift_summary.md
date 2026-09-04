# M4 — drift report

- generated: `2026-09-04T11:23:21+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-04T10:00:00+00:00` (3,172 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.052 |
| target | 🟡 warn | actual demand PSI 0.106, mean moved +4,227 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.031, mean moved +1,038 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,298 MWh (+16.1%), MAPE +0.30 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.0516 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.0129 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9191 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.8316 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.7090 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5220 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4090 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.3672 | 0.00e+00 | alert |
