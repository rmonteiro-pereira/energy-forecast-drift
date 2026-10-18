# M4 — drift report

- generated: `2026-10-18T11:14:15+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-18T10:00:00+00:00` (7,396 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 18/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.759 |
| target | 🔴 alert | actual demand PSI 0.279, mean moved -5,626 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.345, mean moved -7,981 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,046 MWh (+7.3%), MAPE +0.31 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7593 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.9595 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.5455 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.0021 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.9238 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.9207 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.6413 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.6330 | 0.00e+00 | alert |
