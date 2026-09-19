# M4 — drift report

- generated: `2026-09-19T11:05:26+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-19T10:00:00+00:00` (4,612 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.413 |
| target | 🟡 warn | actual demand PSI 0.053, mean moved +2,466 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.026, mean moved -597 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,534 MWh (+24.4%), MAPE +0.58 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.4127 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.5393 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8218 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5927 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4521 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.4402 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.3569 | 0.00e+00 | alert |
| `wind_fcst_target` | 0.3052 | 0.00e+00 | alert |
