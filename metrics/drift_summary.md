# M4 — drift report

- generated: `2026-08-14T07:53:32+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-14T07:00:00+00:00` (1,132 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature, target drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 21/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.636 |
| target | 🔴 alert | actual demand PSI 0.515, mean moved +7,443 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.153, mean moved +4,118 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,448 MWh (+21.4%), MAPE +0.36 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6359 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.3928 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 6.3047 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 5.2126 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 4.9396 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 4.2338 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 2.9275 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 2.6846 | 0.00e+00 | alert |
