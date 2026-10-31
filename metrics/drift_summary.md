# M4 — drift report

- generated: `2026-10-31T12:40:07+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-31T11:00:00+00:00` (8,644 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 17/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.850 |
| target | 🔴 alert | actual demand PSI 0.443, mean moved -7,888 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 0.561, mean moved -10,241 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 2,886 MWh (+1.6%), MAPE +0.21 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8504 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 5.1498 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.8568 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.3033 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.2182 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 1.2173 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.8589 | 0.00e+00 | alert |
| `temp_last_1h` | 0.8303 | 0.00e+00 | alert |
