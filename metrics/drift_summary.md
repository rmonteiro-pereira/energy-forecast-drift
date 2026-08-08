# M4 — drift report

- generated: `2026-08-08T07:18:23+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-08T06:00:00+00:00` (556 rows)


## Verdict: 🔴 **RETRAIN** (`R1_performance_alert`)

The frozen model's rolling error crossed the degradation alert line. That is measured harm, so it triggers a retrain on its own.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 19/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.044 |
| target | 🔴 alert | actual demand PSI 0.424, mean moved +6,969 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.079, mean moved +2,501 MWh (label-free signal: available before the actuals arrive) |
| performance | 🔴 alert | MAE 2,840 -> 4,119 MWh (+45.0%), MAPE +0.94 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.0438 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 10.0091 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 6.3834 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 5.2885 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.9959 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.8769 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 3.9880 | 0.00e+00 | alert |
| `temp_last_1h` | 3.8814 | 0.00e+00 | alert |
