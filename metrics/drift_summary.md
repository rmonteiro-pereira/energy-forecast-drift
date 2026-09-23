# M4 — drift report

- generated: `2026-09-23T11:43:49+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-23T10:00:00+00:00` (4,996 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.480 |
| target | 🟡 warn | actual demand PSI 0.043, mean moved +1,290 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.041, mean moved -1,573 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,463 MWh (+21.9%), MAPE +0.54 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.4802 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.5737 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8624 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5171 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4753 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.3757 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.3571 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.3144 | 0.00e+00 | alert |
