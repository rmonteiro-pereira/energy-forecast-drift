# M4 — drift report

- generated: `2026-10-13T14:17:50+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-13T13:00:00+00:00` (6,916 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 18/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.717 |
| target | 🔴 alert | actual demand PSI 0.249, mean moved -4,889 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.300, mean moved -7,238 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,043 MWh (+7.2%), MAPE +0.28 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7169 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.8808 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.4132 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.8734 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.8012 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.7953 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5891 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.5502 | 0.00e+00 | alert |
