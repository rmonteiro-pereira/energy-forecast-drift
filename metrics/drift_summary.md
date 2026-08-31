# M4 — drift report

- generated: `2026-08-31T13:57:58+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-31T13:00:00+00:00` (2,788 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.959 |
| target | 🟡 warn | actual demand PSI 0.065, mean moved +2,864 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.015, mean moved -154 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,163 MWh (+11.4%), MAPE +0.23 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.9592 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 6.1445 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 0.9858 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.6647 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.6149 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.6119 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.4157 | 0.00e+00 | alert |
| `demand_same_hour_of_week_mean_4w` | 0.3933 | 0.00e+00 | alert |
