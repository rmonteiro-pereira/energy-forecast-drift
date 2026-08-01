# M4 — drift report

- generated: `2026-08-01T21:47:38+00:00`
- source: `eia_api_v2`
- reference: `2026-06-20T20:00:00+00:00` → `2026-07-18T20:00:00+00:00` (2,688 rows)
- current: `2026-07-18T20:00:00+00:00` → `2026-08-01T20:00:00+00:00` (1,292 rows)


## Verdict: 🔴 **RETRAIN** (`R1_performance_alert`)

The frozen model's rolling error crossed the degradation alert line. That is measured harm, so it triggers a retrain on its own.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 11/14 feature(s) above PSI 0.2; worst is demand_roll_mean_168h at PSI 5.390 |
| target | 🔴 alert | actual demand PSI 1.315, mean moved -7,031 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.149, mean moved -2,201 MWh (label-free signal: available before the actuals arrive) |
| performance | 🔴 alert | MAE 4,852 -> 5,894 MWh (+21.5%), MAPE +1.41 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_mean_168h` | 5.3901 | 0.00e+00 | alert |
| `demand_roll_max_24h` | 4.4224 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.1734 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 4.0551 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 3.8247 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 3.1460 | 0.00e+00 | alert |
| `demand_lag_336h` | 1.4857 | 0.00e+00 | alert |
| `temp_last_1h` | 1.4620 | 0.00e+00 | alert |
