# M4 — drift report

- generated: `2026-09-03T11:20:38+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-03T10:00:00+00:00` (3,076 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.030 |
| target | 🟡 warn | actual demand PSI 0.092, mean moved +3,813 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.023, mean moved +624 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,283 MWh (+15.6%), MAPE +0.30 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.0304 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.9918 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9212 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.7829 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.6912 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5109 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4082 | 0.00e+00 | alert |
| `wind_fcst_target` | 0.3614 | 0.00e+00 | alert |
