# M4 — drift report

- generated: `2026-08-09T07:19:09+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-09T06:00:00+00:00` (652 rows)


## Verdict: 🔴 **RETRAIN** (`R1_performance_alert`)

The frozen model's rolling error crossed the degradation alert line. That is measured harm, so it triggers a retrain on its own.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 20/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.225 |
| target | 🔴 alert | actual demand PSI 0.478, mean moved +7,394 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.110, mean moved +3,189 MWh (label-free signal: available before the actuals arrive) |
| performance | 🔴 alert | MAE 2,840 -> 3,884 MWh (+36.8%), MAPE +0.73 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.2246 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.5931 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 6.3334 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 5.3747 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 5.0652 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.8176 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 4.0961 | 0.00e+00 | alert |
| `temp_last_1h` | 3.9427 | 0.00e+00 | alert |
