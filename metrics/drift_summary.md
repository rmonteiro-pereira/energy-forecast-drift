# M4 — drift report

- generated: `2026-09-30T12:41:20+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-09-30T11:00:00+00:00` (5,668 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.579 |
| target | 🟡 warn | actual demand PSI 0.096, mean moved -1,497 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.113, mean moved -3,983 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,242 MWh (+14.1%), MAPE +0.39 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.5788 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.6712 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.0456 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5273 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.5099 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5000 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.4529 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.3214 | 0.00e+00 | alert |
