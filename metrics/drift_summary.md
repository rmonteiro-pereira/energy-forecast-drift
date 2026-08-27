# M4 — drift report

- generated: `2026-08-27T17:40:28+00:00`
- source: `eia_api_v2`
- reference: `2026-07-19T00:00:00+00:00` → `2026-08-02T00:00:00+00:00` (1,344 rows)
- current: `2026-08-02T00:00:00+00:00` → `2026-08-27T16:00:00+00:00` (2,428 rows)


## Verdict: 🟡 **WATCH** (`R4_watch`)

Drift is visible but no rule for retraining is satisfied: a single distribution signal without measured degradation is a leading indicator, not proof of harm. Recorded and charted, not acted on.

Worst signal severity: `alert`. Retrain now? **no**.


| Drift type | Severity | Summary |
|---|---|---|
| feature | 🔴 alert | 16/21 feature(s) above PSI 0.2; worst is demand_roll_max_24h at PSI 22.849 |
| target | 🟡 warn | actual demand PSI 0.092, mean moved +3,584 MWh between the reference and current windows |
| prediction | 🟢 ok | forecast PSI 0.023, mean moved +436 MWh (label-free signal: available before the actuals arrive) |
| performance | 🟢 ok | MAE 2,840 -> 3,166 MWh (+11.5%), MAPE +0.21 pp |

### Worst features by PSI

| Feature | PSI | KS p | Severity |
|---|---:|---:|---|
| `demand_roll_max_24h` | 22.8490 | 0.00e+00 | alert |
| `demand_roll_mean_168h` | 6.3236 | 0.00e+00 | alert |
| `temp_roll_mean_24h` | 1.7330 | 0.00e+00 | alert |
| `demand_roll_min_24h` | 1.0818 | 0.00e+00 | alert |
| `dewpoint_fcst_target` | 0.8109 | 0.00e+00 | alert |
| `demand_roll_std_24h` | 0.7449 | 0.00e+00 | alert |
| `temp_fcst_target_minus_lag_168h` | 0.6510 | 0.00e+00 | alert |
| `temp_last_1h` | 0.4820 | 0.00e+00 | alert |
