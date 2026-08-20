# M4 — drift report

- generated: `2026-08-20T07:09:40+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-20T06:00:00+00:00` (1,708 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature, target drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 20/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.506 |
| target | 🔴 alert | actual demand PSI 0.510, mean moved +6,742 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.117, mean moved +3,375 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,388 MWh (+19.3%), MAPE +0.33 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.5055 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.5246 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 5.6813 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.9875 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.1022 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 2.7786 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 1.7870 | 0.00e+00 | alert |
| `temp_last_1h` | 1.7694 | 0.00e+00 | alert |
