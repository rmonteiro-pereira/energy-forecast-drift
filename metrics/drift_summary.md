# M4 — drift report

- generated: `2026-10-05T14:48:05+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-05T13:00:00+00:00` (6,148 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.638 |
| target | 🟡 warn | actual demand PSI 0.136, mean moved -2,717 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.163, mean moved -5,121 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,209 MWh (+13.0%), MAPE +0.39 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6376 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.7511 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.1890 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.6535 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5988 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.5851 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5244 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.4152 | 0.00e+00 | alert |
