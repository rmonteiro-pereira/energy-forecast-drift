# M4 — drift report

- generated: `2026-09-24T11:52:54+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-24T11:00:00+00:00` (5,092 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.496 |
| target | 🟡 warn | actual demand PSI 0.044, mean moved +890 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.045, mean moved -1,878 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,451 MWh (+21.5%), MAPE +0.54 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.4956 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.5856 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8853 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4775 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.4339 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.3930 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.3408 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.3333 | 0.00e+00 | alert |
