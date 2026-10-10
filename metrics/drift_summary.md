# M4 — drift report

- generated: `2026-10-10T12:37:55+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-10T11:00:00+00:00` (6,628 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.689 |
| target | 🔴 alert | actual demand PSI 0.203, mean moved -4,094 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.246, mean moved -6,442 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,073 MWh (+8.2%), MAPE +0.29 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6890 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.8325 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.3307 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.7929 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.7258 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.7175 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5577 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.4898 | 0.00e+00 | alert |
