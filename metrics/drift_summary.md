# M4 — drift report

- generated: `2026-09-05T10:40:26+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-05T09:00:00+00:00` (3,268 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.072 |
| target | 🟡 warn | actual demand PSI 0.118, mean moved +4,567 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.038, mean moved +1,357 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,324 MWh (+17.1%), MAPE +0.32 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.0716 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.0400 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9276 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.8817 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.7248 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5501 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4107 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.3899 | 0.00e+00 | alert |
