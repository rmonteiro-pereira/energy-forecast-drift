# M4 — drift report

- generated: `2026-10-25T11:38:20+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-25T10:00:00+00:00` (8,068 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.811 |
| target | 🔴 alert | actual demand PSI 0.381, mean moved -6,963 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.465, mean moved -9,299 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,945 MWh (+3.7%), MAPE +0.24 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8113 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.0648 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.7190 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.1701 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.0866 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.0861 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.7399 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.7373 | 0.00e+00 | alert |
