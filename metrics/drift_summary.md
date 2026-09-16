# M4 — drift report

- generated: `2026-09-16T11:42:20+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-16T10:00:00+00:00` (4,324 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.355 |
| target | 🟡 warn | actual demand PSI 0.067, mean moved +2,619 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.030, mean moved -317 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,444 MWh (+21.3%), MAPE +0.49 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.3552 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.6320 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.8063 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.5688 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.4904 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4512 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.4010 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.3113 | 0.00e+00 | alert |
