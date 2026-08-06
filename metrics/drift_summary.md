# M4 — drift report

- generated: `2026-08-06T09:09:09+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-06T08:00:00+00:00` (364 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature, target drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 19/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.418 |
| target | 🔴 alert | actual demand PSI 0.263, mean moved +3,217 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.046, mean moved -608 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,590 MWh (+26.4%), MAPE +0.57 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.4176 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 11.2121 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 8.0584 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 7.9585 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 7.8447 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 5.2117 | 0.00e+00 | alert |
| `temp_last_1h` | 4.7157 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.3514 | 0.00e+00 | alert |
