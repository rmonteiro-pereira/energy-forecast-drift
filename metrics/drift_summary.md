# M4 — drift report

- generated: `2026-10-08T13:36:47+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-08T12:00:00+00:00` (6,436 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

2 distribution signals are alerting (feature, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.669 |
| target | 🟡 warn | actual demand PSI 0.180, mean moved -3,590 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.216, mean moved -5,964 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,124 MWh (+10.0%), MAPE +0.33 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6693 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.7999 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.2745 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.7378 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.6750 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.6649 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5473 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.4698 | 0.00e+00 | alert |
