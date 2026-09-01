# M4 — drift report

- generated: `2026-09-01T11:43:38+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-01T10:00:00+00:00` (2,884 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.984 |
| target | 🟡 warn | actual demand PSI 0.067, mean moved +2,955 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.014, mean moved -132 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,209 MWh (+13.0%), MAPE +0.27 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.9844 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 6.1357 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9046 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.6897 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.6350 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5625 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.3979 | 0.00e+00 | alert |
| `temp_last_1h` | 0.3935 | 0.00e+00 | alert |
