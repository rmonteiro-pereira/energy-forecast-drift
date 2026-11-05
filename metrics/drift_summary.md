# M4 — drift report

- generated: `2026-11-05T14:43:18+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-11-05T14:00:00+00:00` (9,124 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.880 |
| target | 🔴 alert | actual demand PSI 0.505, mean moved -8,629 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.631, mean moved -10,942 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,815 MWh (-0.9%), MAPE +0.16 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8799 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.2170 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.9645 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.4073 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.3218 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.3201 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.9542 | 0.00e+00 | alert |
| `temp_last_1h` | 0.9230 | 0.00e+00 | alert |
