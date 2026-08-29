# M4 — drift report

- generated: `2026-08-29T12:43:30+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-29T11:00:00+00:00` (2,596 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 15/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.904 |
| target | 🟡 warn | actual demand PSI 0.091, mean moved +3,540 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.020, mean moved +411 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,133 MWh (+10.3%), MAPE +0.19 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.9039 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 6.1962 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.0283 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.7627 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.6372 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.6364 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 0.6183 | 0.00e+00 | alert |
| `humidity_fcst_target` | 0.4335 | 0.00e+00 | alert |
