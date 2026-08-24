# M4 — drift report

- generated: `2026-08-24T07:31:12+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-24T06:00:00+00:00` (2,092 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 19/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.716 |
| target | 🟡 warn | actual demand PSI 0.178, mean moved +5,095 MWh between the reference and current windows |
| prediction | 🟡 warn | forecast PSI 0.050, mean moved +1,942 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,227 MWh (+13.6%), MAPE +0.23 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.7156 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 9.5367 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 2.7152 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 2.4929 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.8421 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 1.6802 | 0.00e+00 | alert |
| `demand_roll_mean_24h` | 1.6707 | 0.00e+00 | alert |
| `humidity_fcst_target` | 0.7378 | 0.00e+00 | alert |
