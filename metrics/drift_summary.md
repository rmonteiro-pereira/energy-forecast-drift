# M4 — drift report

- generated: `2026-09-07T12:40:23+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-07T11:00:00+00:00` (3,460 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.109 |
| target | 🟡 warn | actual demand PSI 0.104, mean moved +4,132 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.032, mean moved +1,196 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,306 MWh (+16.4%), MAPE +0.32 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.1087 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.0942 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9444 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.8496 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.7454 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5865 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.4263 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4235 | 0.00e+00 | alert |
