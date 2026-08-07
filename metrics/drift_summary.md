# M4 — drift report

- generated: `2026-08-07T07:44:40+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-07T06:00:00+00:00` (460 rows)


## Verdict: 🔴 **RETRAIN** (`R1_performance_alert`)

The frozen model's rolling error crossed the degradation alert line. That is measured harm, so it triggers a retrain on its own.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 19/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.792 |
| target | 🔴 alert | actual demand PSI 0.339, mean moved +5,213 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.043, mean moved +909 MWh (label-free signal: available before the actuals arrive) |
| performance | 🔴 alert | MAE 2,840 -> 3,995 MWh (+40.7%), MAPE +0.88 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7925 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 11.2801 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 7.8730 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 6.3455 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 5.3447 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 5.1590 | 0.00e+00 | alert |
| `temp_last_1h` | 4.8075 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.6296 | 0.00e+00 | alert |
