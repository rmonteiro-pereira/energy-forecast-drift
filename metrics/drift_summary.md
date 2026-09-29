# M4 — drift report

- generated: `2026-09-29T12:59:02+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-29T12:00:00+00:00` (5,572 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.566 |
| target | 🟡 warn | actual demand PSI 0.091, mean moved -1,219 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.105, mean moved -3,728 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,285 MWh (+15.7%), MAPE +0.43 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.5660 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.6558 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.0174 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5027 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.4954 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.4811 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.4272 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.3076 | 0.00e+00 | alert |
