# M4 — drift report

- generated: `2026-08-28T18:46:39+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-28T17:00:00+00:00` (2,524 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.881 |
| target | 🟡 warn | actual demand PSI 0.093, mean moved +3,584 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.023, mean moved +411 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,180 MWh (+12.0%), MAPE +0.23 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8812 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 6.2357 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.0012 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.7820 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.6709 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.6504 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.6345 | 0.00e+00 | alert |
| `temp_last_1h` | 0.4674 | 0.00e+00 | alert |
