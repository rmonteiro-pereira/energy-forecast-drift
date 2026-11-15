# M4 — drift report

- generated: `2026-11-15T14:02:00+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-11-15T13:00:00+00:00` (10,084 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.932 |
| target | 🔴 alert | actual demand PSI 0.576, mean moved -9,529 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.728, mean moved -11,855 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,743 MWh (-3.4%), MAPE +0.11 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.9316 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.3418 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 2.1620 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.5980 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.5126 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.5100 | 0.00e+00 | alert |
| `temp_lag_168h` | 1.1230 | 0.00e+00 | alert |
| `temp_last_1h` | 1.1076 | 0.00e+00 | alert |
