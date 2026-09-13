# M4 — drift report

- generated: `2026-09-13T11:57:44+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-13T11:00:00+00:00` (4,036 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.290 |
| target | 🟡 warn | actual demand PSI 0.083, mean moved +3,338 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.026, mean moved +366 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,409 MWh (+20.0%), MAPE +0.44 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.2905 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.8858 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9276 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.5841 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5676 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.4524 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4362 | 0.00e+00 | alert |
| `demand_lag_336h` | 0.3428 | 0.00e+00 | alert |
