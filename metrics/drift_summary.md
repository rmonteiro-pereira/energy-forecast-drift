# M4 — drift report

- generated: `2026-08-19T07:08:47+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-19T06:00:00+00:00` (1,612 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature, target drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 20/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.439 |
| target | 🔴 alert | actual demand PSI 0.505, mean moved +6,773 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.108, mean moved +3,331 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,475 MWh (+22.4%), MAPE +0.41 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.4388 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.5013 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 5.6527 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.9728 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.3681 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 2.7271 | 0.00e+00 | alert |
| `temp_last_1h` | 1.8094 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 1.7761 | 0.00e+00 | alert |
