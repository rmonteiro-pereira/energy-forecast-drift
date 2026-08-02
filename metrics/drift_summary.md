# M4 — drift report

- generated: `2026-08-02T02:42:15+00:00`
- source: `eia_api_v2`
- reference: `2026-07-05T01:00:00+00:00` → `2026-07-19T01:00:00+00:00` (1,344 rows)
- current: `2026-07-19T01:00:00+00:00` → `2026-08-02T01:00:00+00:00` (1,296 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 23.819 |
| target | 🔴 alert | actual demand PSI 1.473, mean moved -10,540 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.452, mean moved -8,905 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 3,571 -> 2,655 MWh (-25.7%), MAPE -0.55 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 23.8190 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 23.3574 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.1074 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 4.6423 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 4.3185 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 3.7492 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 2.7493 | 0.00e+00 | alert |
| `temp_last_1h` | 1.7430 | 0.00e+00 | alert |
