# M4 — drift report

- generated: `2026-09-10T11:25:30+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-10T10:00:00+00:00` (3,748 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.158 |
| target | 🟡 warn | actual demand PSI 0.088, mean moved +3,496 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.030, mean moved +421 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,461 MWh (+21.9%), MAPE +0.48 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.1580 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.1592 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9442 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.6801 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5566 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5033 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4281 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.3594 | 0.00e+00 | alert |
