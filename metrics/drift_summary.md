# M4 — drift report

- generated: `2026-09-14T12:56:35+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-14T12:00:00+00:00` (4,132 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.313 |
| target | 🟡 warn | actual demand PSI 0.077, mean moved +3,149 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.027, mean moved +126 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,445 MWh (+21.3%), MAPE +0.48 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.3129 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.8793 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8991 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.5854 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5603 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4433 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.4428 | 0.00e+00 | alert |
| `demand_lag_336h` | 0.3566 | 0.00e+00 | alert |
