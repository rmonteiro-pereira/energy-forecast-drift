# M4 — drift report

- generated: `2026-10-01T13:24:28+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-01T12:00:00+00:00` (5,764 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.591 |
| target | 🟡 warn | actual demand PSI 0.100, mean moved -1,733 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.121, mean moved -4,204 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,209 MWh (+13.0%), MAPE +0.36 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.5912 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.6869 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.0741 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.5523 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.5388 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5033 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.4789 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.3391 | 0.00e+00 | alert |
