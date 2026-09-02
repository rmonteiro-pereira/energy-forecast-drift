# M4 — drift report

- generated: `2026-09-02T11:24:09+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-02T10:00:00+00:00` (2,980 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.008 |
| target | 🟡 warn | actual demand PSI 0.079, mean moved +3,361 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.016, mean moved +179 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,282 MWh (+15.6%), MAPE +0.31 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.0081 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.0088 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9404 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.7346 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.6648 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5195 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4031 | 0.00e+00 | alert |
| `temp_last_1h` | 0.3820 | 0.00e+00 | alert |
