# M4 — drift report

- generated: `2026-10-23T11:44:53+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-23T10:00:00+00:00` (7,876 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.797 |
| target | 🔴 alert | actual demand PSI 0.349, mean moved -6,589 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.429, mean moved -8,918 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,968 MWh (+4.5%), MAPE +0.25 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7972 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.0354 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.6708 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.1235 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.0412 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.0400 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.7102 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.6959 | 0.00e+00 | alert |
