# M4 — drift report

- generated: `2026-11-19T15:49:34+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-11-19T15:00:00+00:00` (10,492 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.951 |
| target | 🔴 alert | actual demand PSI 0.575, mean moved -9,657 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.743, mean moved -12,018 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,742 MWh (-3.5%), MAPE +0.12 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.9513 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.3912 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 2.0463 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.6728 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.5876 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.5849 | 0.00e+00 | alert |
| `temp_lag_168h` | 1.1964 | 0.00e+00 | alert |
| `temp_last_1h` | 1.1836 | 0.00e+00 | alert |
