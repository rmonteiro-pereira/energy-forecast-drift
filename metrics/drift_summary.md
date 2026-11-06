# M4 — drift report

- generated: `2026-11-06T14:21:26+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-11-06T13:00:00+00:00` (9,220 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.885 |
| target | 🔴 alert | actual demand PSI 0.511, mean moved -8,729 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.639, mean moved -11,032 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,799 MWh (-1.4%), MAPE +0.14 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8854 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.2300 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.9853 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.4274 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.3418 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.3400 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.9683 | 0.00e+00 | alert |
| `temp_last_1h` | 0.9372 | 0.00e+00 | alert |
