# M4 — drift report

- generated: `2026-10-04T12:27:23+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-04T11:00:00+00:00` (6,052 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 14/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.626 |
| target | 🟡 warn | actual demand PSI 0.119, mean moved -2,339 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.147, mean moved -4,785 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,221 MWh (+13.4%), MAPE +0.40 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6265 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.7349 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.1603 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.6250 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.6033 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.5584 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5165 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.3943 | 0.00e+00 | alert |
