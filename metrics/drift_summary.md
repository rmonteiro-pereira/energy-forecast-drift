# M4 — drift report

- generated: `2026-10-02T12:43:05+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-02T11:00:00+00:00` (5,860 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.603 |
| target | 🟡 warn | actual demand PSI 0.103, mean moved -1,892 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.128, mean moved -4,390 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,214 MWh (+13.2%), MAPE +0.37 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6033 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.7027 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.1028 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5777 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.5676 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5062 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.5053 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.3580 | 0.00e+00 | alert |
