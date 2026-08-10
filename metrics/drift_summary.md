# M4 — drift report

- generated: `2026-08-10T08:07:34+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-10T07:00:00+00:00` (748 rows)


## Verdict: 🔴 **RETRAIN** (`R1_performance_alert`)

The frozen model's rolling error crossed the degradation alert line. That is measured harm, so it triggers a retrain on its own.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 20/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.361 |
| target | 🔴 alert | actual demand PSI 0.488, mean moved +7,345 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.111, mean moved +3,288 MWh (label-free signal: available before the actuals arrive) |
| performance | 🔴 alert | MAE 2,840 -> 3,798 MWh (+33.7%), MAPE +0.66 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.3613 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.4539 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 6.3357 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 5.2666 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.8627 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 4.2082 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.1705 | 0.00e+00 | alert |
| `temp_last_1h` | 2.9297 | 0.00e+00 | alert |
