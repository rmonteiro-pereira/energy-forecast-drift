# M4 — drift report

- generated: `2026-10-06T13:22:54+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-10-06T12:00:00+00:00` (6,244 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.648 |
| target | 🟡 warn | actual demand PSI 0.150, mean moved -3,023 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.181, mean moved -5,419 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,183 MWh (+12.1%), MAPE +0.38 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.6484 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 4.7674 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.2177 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.6818 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.6241 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 0.6117 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.5327 | 0.00e+00 | alert |
| `temp_lag_168h` | 0.4366 | 0.00e+00 | alert |
