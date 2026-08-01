# M2 — LightGBM vs the seasonal-naive baseline

> ⚠️ **SYNTHETIC — NOT REAL DATA.** These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. They are a smoke test of the pipeline, NOT a benchmark. The real baseline is pending the EIA API key — see docs/BLOCKED.md.

- generated: `2026-08-01T23:32:37+00:00`
- source: `synthetic_fixture`
- protocol: 56 daily folds x 24 horizons, identical for both models
- overall MAE: baseline **2,559** -> LightGBM **2,194** MWh (-14.3%)
- horizons where LightGBM wins: 24/24

| Horizon (h) | Baseline MAE | LightGBM MAE | Delta | Delta % |
|---:|---:|---:|---:|---:|
| 1 | 2,621 | 2,070 | -551 | -21.0 |
| 2 | 2,932 | 2,280 | -651 | -22.2 |
| 3 | 2,310 | 2,078 | -232 | -10.1 |
| 4 | 2,533 | 2,220 | -313 | -12.4 |
| 5 | 2,204 | 2,003 | -201 | -9.1 |
| 6 | 2,491 | 2,146 | -345 | -13.9 |
| 7 | 2,904 | 2,372 | -533 | -18.3 |
| 8 | 2,512 | 2,247 | -265 | -10.6 |
| 9 | 2,648 | 2,303 | -345 | -13.0 |
| 10 | 2,381 | 2,300 | -82 | -3.4 |
| 11 | 3,127 | 2,441 | -686 | -21.9 |
| 12 | 2,681 | 2,611 | -70 | -2.6 |
| 13 | 2,375 | 2,230 | -145 | -6.1 |
| 14 | 2,633 | 2,138 | -496 | -18.8 |
| 15 | 1,928 | 1,710 | -218 | -11.3 |
| 16 | 2,474 | 2,107 | -367 | -14.8 |
| 17 | 2,643 | 1,943 | -700 | -26.5 |
| 18 | 2,906 | 2,192 | -713 | -24.6 |
| 19 | 2,576 | 2,118 | -459 | -17.8 |
| 20 | 2,357 | 1,985 | -371 | -15.8 |
| 21 | 2,376 | 1,875 | -501 | -21.1 |
| 22 | 2,337 | 2,252 | -84 | -3.6 |
| 23 | 2,628 | 2,343 | -285 | -10.8 |
| 24 | 2,844 | 2,691 | -153 | -5.4 |
