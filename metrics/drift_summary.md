# M4 — drift report

- generated: `2026-10-14T12:00:52+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-14T11:00:00+00:00` (7,012 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 18/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.726 |
| target | 🔴 alert | actual demand PSI 0.252, mean moved -5,011 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.308, mean moved -7,387 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,054 MWh (+7.5%), MAPE +0.30 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7258 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.8967 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.4402 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.8997 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.8261 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.8208 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.6002 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.5714 | 0.00e+00 | alert |
