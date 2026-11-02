# M4 — drift report

- generated: `2026-11-02T16:04:16+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-11-02T15:00:00+00:00` (8,860 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.864 |
| target | 🔴 alert | actual demand PSI 0.482, mean moved -8,312 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.603, mean moved -10,653 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,859 MWh (+0.7%), MAPE +0.19 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8640 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.1805 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.9060 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.3509 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.2655 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.2643 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.9034 | 0.00e+00 | alert |
| `temp_last_1h` | 0.8763 | 0.00e+00 | alert |
