# M2 — LightGBM vs the seasonal-naive baseline

> ⚠️ **SYNTHETIC — NOT REAL DATA.** These numbers come from a SEEDED SYNTHETIC FIXTURE, not from EIA data. They are a smoke test of the pipeline, NOT a benchmark. The real baseline is pending the EIA API key — see docs/BLOCKED.md.

- generated: `2026-07-29T04:49:37+00:00`
- source: `synthetic_fixture`
- protocol: 56 daily folds x 24 horizons, identical for both models
- overall MAE: baseline **2,559** -> LightGBM **2,181** MWh (-14.8%)
- horizons where LightGBM wins: 23/24

| Horizon (h) | Baseline MAE | LightGBM MAE | Delta | Delta % |
|---:|---:|---:|---:|---:|
| 1 | 2,621 | 2,056 | -565 | -21.6 |
| 2 | 2,932 | 2,375 | -556 | -19.0 |
| 3 | 2,310 | 2,097 | -213 | -9.2 |
| 4 | 2,533 | 2,132 | -400 | -15.8 |
| 5 | 2,204 | 1,937 | -267 | -12.1 |
| 6 | 2,491 | 2,118 | -373 | -15.0 |
| 7 | 2,904 | 2,320 | -585 | -20.1 |
| 8 | 2,512 | 2,228 | -284 | -11.3 |
| 9 | 2,648 | 2,302 | -346 | -13.1 |
| 10 | 2,381 | 2,391 | +10 | +0.4 |
| 11 | 3,127 | 2,384 | -744 | -23.8 |
| 12 | 2,681 | 2,581 | -101 | -3.8 |
| 13 | 2,375 | 2,195 | -180 | -7.6 |
| 14 | 2,633 | 2,259 | -374 | -14.2 |
| 15 | 1,928 | 1,745 | -182 | -9.5 |
| 16 | 2,474 | 1,992 | -482 | -19.5 |
| 17 | 2,643 | 1,874 | -769 | -29.1 |
| 18 | 2,906 | 2,103 | -802 | -27.6 |
| 19 | 2,576 | 2,047 | -529 | -20.5 |
| 20 | 2,357 | 2,102 | -254 | -10.8 |
| 21 | 2,376 | 2,022 | -354 | -14.9 |
| 22 | 2,337 | 2,199 | -138 | -5.9 |
| 23 | 2,628 | 2,283 | -345 | -13.1 |
| 24 | 2,844 | 2,602 | -242 | -8.5 |
