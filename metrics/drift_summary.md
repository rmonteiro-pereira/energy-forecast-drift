# M4 — drift report

- generated: `2026-11-01T13:31:14+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-11-01T12:00:00+00:00` (8,740 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.857 |
| target | 🔴 alert | actual demand PSI 0.459, mean moved -8,075 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.580, mean moved -10,423 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,873 MWh (+1.2%), MAPE +0.20 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8565 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.1635 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.8789 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.3246 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.2394 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.2383 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.8788 | 0.00e+00 | alert |
| `temp_last_1h` | 0.8508 | 0.00e+00 | alert |
