# M4 — drift report

- generated: `2026-10-20T11:45:03+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-20T10:00:00+00:00` (7,588 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 18/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.775 |
| target | 🔴 alert | actual demand PSI 0.311, mean moved -6,078 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.382, mean moved -8,411 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,016 MWh (+6.2%), MAPE +0.29 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7749 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.9902 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.5965 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.0515 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.9714 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.9691 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.6722 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.6666 | 0.00e+00 | alert |
