# M4 — drift report

- generated: `2026-08-23T07:04:25+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-23T06:00:00+00:00` (1,996 rows)


## Verdict: 🔴 **RETRAIN** (`R2_distribution_alert_with_performance_warning`)

feature, target drift is alerting and the error is already degrading: a plausible cause with a visible effect.

Worst signal severity: `alert`. Retrain now? **yes**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 20/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.670 |
| target | 🔴 alert | actual demand PSI 0.253, mean moved +5,808 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.071, mean moved +2,581 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟡 warn | MAE 2,840 -> 3,309 MWh (+16.5%), MAPE +0.30 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6701 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.5550 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 4.3180 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 3.4849 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 2.9314 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 2.7197 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 1.6788 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.8526 | 0.00e+00 | alert |
