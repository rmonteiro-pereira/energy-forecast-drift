# M4 — drift report

- generated: `2026-09-28T14:03:44+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-28T13:00:00+00:00` (5,476 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.553 |
| target | 🟡 warn | actual demand PSI 0.083, mean moved -870 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.092, mean moved -3,404 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,324 MWh (+17.0%), MAPE +0.46 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.5528 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.6408 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9895 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4898 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.4788 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.4524 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.4020 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.3163 | 0.00e+00 | alert |
