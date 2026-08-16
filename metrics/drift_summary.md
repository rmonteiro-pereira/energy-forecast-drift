# M4 — drift report

- generated: `2026-08-16T07:02:03+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-16T06:00:00+00:00` (1,324 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature, target drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 20/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.186 |
| target | 🔴 alert | actual demand PSI 0.517, mean moved +7,276 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.138, mean moved +3,864 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,467 MWh (+22.1%), MAPE +0.39 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.1856 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.4317 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 6.3493 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 5.2389 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.9665 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.2698 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 2.6460 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.8994 | 0.00e+00 | alert |
