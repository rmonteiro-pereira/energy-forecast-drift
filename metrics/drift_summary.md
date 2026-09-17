# M4 — drift report

- generated: `2026-09-17T11:47:33+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-17T10:00:00+00:00` (4,420 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.375 |
| target | 🟡 warn | actual demand PSI 0.062, mean moved +2,490 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.031, mean moved -519 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,498 MWh (+23.2%), MAPE +0.54 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.3751 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.5348 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8235 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5806 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.4617 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4512 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.3765 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.3202 | 0.00e+00 | alert |
