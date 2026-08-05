# M4 — drift report

- generated: `2026-08-05T09:09:06+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-04T17:00:00+00:00` (220 rows)


## Verdict: 🟡 **WATCH** (`R3b_distribution_without_measured_harm`)

3 distribution signals are alerting (feature, target, prediction), but the frozen model's error was measured over the same windows and did not degrade. Inputs moved and the model tracked them: that is drift worth watching, not proof the champion needs refitting.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 13/14 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 21.292 |
| target | 🔴 alert | actual demand PSI 0.317, mean moved +698 MWh between the reference and current windows |
| prediction | 🔴 alert | forecast PSI 1.301, mean moved -2,522 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,142 MWh (+10.6%), MAPE +0.18 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 21.2922 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 11.0456 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 9.5120 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 8.1014 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 7.8398 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 6.4094 | 0.00e+00 | alert |
| `demand_last_1h` | 6.2444 | 3.00e-08 | alert |
| `dewpoint_fcst_target` | 5.1672 | 0.00e+00 | ok |
