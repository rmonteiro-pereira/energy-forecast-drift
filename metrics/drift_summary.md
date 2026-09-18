# M4 — drift report

- generated: `2026-09-18T11:23:01+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-18T10:00:00+00:00` (4,516 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.394 |
| target | 🟡 warn | actual demand PSI 0.057, mean moved +2,490 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.029, mean moved -578 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,536 MWh (+24.5%), MAPE +0.58 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.3942 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.5356 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8053 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5906 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4502 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.4411 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.3860 | 0.00e+00 | alert |
| `wind_fcst_target` | 0.3154 | 0.00e+00 | alert |
