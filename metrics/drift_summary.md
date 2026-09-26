# M4 — drift report

- generated: `2026-09-26T11:29:59+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-26T10:00:00+00:00` (5,284 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.525 |
| target | 🟡 warn | actual demand PSI 0.056, mean moved +61 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.061, mean moved -2,561 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,401 MWh (+19.7%), MAPE +0.52 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.5251 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.6120 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9356 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4776 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.4334 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.3957 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.3537 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.3231 | 0.00e+00 | alert |
