# M4 — drift report

- generated: `2026-11-17T16:06:45+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-11-17T15:00:00+00:00` (10,300 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.942 |
| target | 🔴 alert | actual demand PSI 0.580, mean moved -9,625 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.740, mean moved -11,962 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,736 MWh (-3.7%), MAPE +0.11 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.9422 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.3682 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 2.0899 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.6380 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.5527 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.5501 | 0.00e+00 | alert |
| `temp_lag_168h` | 1.1622 | 0.00e+00 | alert |
| `temp_last_1h` | 1.1482 | 0.00e+00 | alert |
