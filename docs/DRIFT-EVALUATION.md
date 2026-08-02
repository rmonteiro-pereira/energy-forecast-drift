# Drift evaluation against drift nobody designed

> [!IMPORTANT]
> **The finding: on real data, the shipped thresholds alarm on two of the three
> control windows where nothing meaningful changed.** A fortnight of ordinary
> autumn cooling scores PSI 0.525 against an alert threshold of 0.20. The
> detector as configured is closer to a season clock than a drift monitor.
>
> This page is the evidence for that, including the windows where it was right.

## Why this exists

Every other drift number in this repository is measured on a synthetic series,
and in two of the tests the shift is **injected by hand** — the detector is asked
to find a change the test author deliberately put there. That proves the
arithmetic. It proves nothing about whether the thresholds are set anywhere near
right, because the size of the shift and the size of the threshold were chosen by
the same person.

So this evaluation uses the one leg of the pipeline that runs on real data today:
**hourly 2 m temperature for Philadelphia, from
[Open-Meteo](https://open-meteo.com/)'s ERA5 reanalysis.**
Real observations, no API key, reproducible by anyone:

```bash
uv run python scripts/drift_eval_real_weather.py
```

> [!CAUTION]
> **This evaluates the detector, not the forecaster.** Temperature is one model
> input, and running the detectors over real weather says nothing about forecast
> quality.
>
> *Updated 2026-08-01.* When this was written, the demand series was synthetic
> too, so the caution read "no other number here is real". The demand leg has
> since gone live and `forecast/monitor/drift/pipeline.json` now carry
> `is_real: true`. What has **not** changed is the sentence that matters for this
> document: no model has been trained on real demand, so `baseline.json` and
> `model.json` are still fixture and the forecaster is still unevaluated.

## Method

Windows were chosen by the calendar, not by looking at the data first, and each
carried a **written expectation before it was run**. Two are true-positive cases,
three are controls where a healthy monitor should stay quiet, and two probe the
small-change regime where a miss is possible.

`A`–`E` were run first. `F` and `G` were added afterwards, because `A`–`E`
produced two clean true positives and no misses — which is weak evidence, since
every shift in them is enormous. Their expectations were written before they ran.
Saying so matters: a pre-registration you extend after seeing results is only
honest if you disclose that you extended it.

Thresholds are the shipped defaults: `psi_warn=0.10`, `psi_alert=0.20`,
`ks_p_alert=0.01`, `min_samples=200`. Every window has 360–744 hourly rows and no
nulls.

## Results

| # | comparison | ref mean | cur mean | shift | rows | PSI | KS p | verdict | expected | |
|---|---|---|---|---|---|---|---|---|---|---|
| A | autumn → winter | 15.15 °C | −1.77 °C | −16.92 °C | 744/744 | 10.57 | ~0 | **alert** | alarm | ✅ |
| B | October → October, a year apart | 15.19 °C | 15.15 °C | −0.04 °C | 744/744 | 0.074 | 0.028 | **ok** | quiet | ✅ |
| C | October → November | 15.15 °C | 10.49 °C | −4.67 °C | 744/720 | 0.705 | ~0 | **alert** | unknown | — |
| D | October 1st half → 2nd half | 16.62 °C | 13.79 °C | −2.83 °C | 360/384 | 0.525 | ~0 | **alert** | quiet | ❌ |
| E | winter → summer | −1.77 °C | 26.67 °C | +28.44 °C | 744/744 | 12.35 | ~0 | **alert** | alarm | ✅ |
| F | January → January, a year apart | 1.90 °C | −1.77 °C | −3.66 °C | 744/744 | 0.603 | ~0 | **alert** | unknown | — |
| G | October 1–15, a year apart | 16.31 °C | 16.62 °C | **+0.30 °C** | 360/360 | 0.177 | 0.022 | **warn** | quiet | ❌ |

### What it caught

**Both true positives, decisively.** The autumn→winter regime change (A) scores
PSI 10.6 and the winter→summer swing (E) scores 12.4 — fifty times the alert
threshold. There is no question of the detector sleeping through a real change of
that size, and the KS test agrees at machine-zero p-values.

**One clean negative.** Matching full months a year apart (B) gives PSI 0.074 and
an `ok` verdict, on a mean difference of 0.04 °C. That is the behaviour the whole
design is aiming for.

**The KS guardrail earned its keep.** In B the KS p-value is 0.028 — significant
at the conventional 0.05 and *not* at the shipped 0.01. Had the alpha been the
textbook default, B would have been dragged to `warn` and the only clean control
would have been lost.
[ADR 0003](adr/0003-own-psi-and-ks-implementations.md) argues that KS "becomes
trivially significant at thousands of rows", which is why PSI triggers and KS only
records. This is that argument happening on real data rather than in prose — and
it is the one design decision here that the evidence straightforwardly supports.

### What it got wrong

**D is a false positive at the highest severity.** The first and second halves of
a single October — a fortnight apart, same place, same season — score PSI 0.525
and alert. Nothing broke, nothing drifted, and the model would have been paged.

**G is worse, because it is quieter.** Two matched fortnights a year apart differ
by **0.30 °C** in the mean, and still score PSI 0.177 → `warn`. Compare B: whole
months, a year apart, a 0.04 °C difference, PSI 0.074 → `ok`.

The difference between B and G is not the data, it is **the window length**. B
has 744 rows per side; G has 360. PSI is computed over quantile bins of the
reference, and on a short window of a strongly autocorrelated, strongly seasonal
variable those bins encode *where in the season the window sits* at least as much
as they encode the distribution. Halve the window and the score sextuples on
essentially identical weather.

That is the concrete, quantified version of a claim the codebase already makes
somewhere else. `DETERMINISTIC_COLUMNS` excludes `hour`, `month` and friends from
voting, on the grounds that their PSI measures which dates the window covers
rather than anything about the data. **This evaluation shows the same objection
applies to weather features, which are seasonal but are not excluded.**

### What it missed

**Nothing — and that is not the reassurance it sounds like.** No real change in
these windows went unflagged. But a detector that alerts on four of five
non-events cannot easily miss anything; the absence of false negatives here is a
*corollary of the false-positive rate*, not independent evidence of sensitivity.

The honest statement is: **this evaluation cannot measure the miss rate.** To do
that you need real changes small enough to be missable and consequential enough
to matter, and on a seasonal variable at these thresholds there is no such band —
everything above noise is already alarming. Measuring misses properly needs the
demand series, which needs the EIA key ([`docs/BLOCKED.md`](BLOCKED.md)).

## What this does and does not license

**It does not mean the code is wrong.** The PSI arithmetic reproduces on demand
(`tests/test_drift_stats.py::test_psi_two_bin_case_matches_the_formula_by_hand`,
plus a cross-check of the KS statistic against SciPy). The defect
is in **calibration**, not computation — the thresholds were taken from the
common industry rule of thumb (0.1 / 0.2) and never checked against a real
seasonal series.

> An earlier version of this paragraph said "the PSI implementation is tested to
> a 61% mutation score". That was wrong, and wrong in the way this document
> exists to complain about. `population_stability_index` lives in
> `drift/stats.py`, and `[tool.mutmut]` mutates `drift/detectors.py` and
> `models/backtest.py` only — so PSI has **no** mutation score. 61.1% is
> `drift/detectors.py`'s, which *calls* PSI and applies the thresholds. The
> number was real; the file it was attached to was not. Corrected rather than
> deleted, because a document arguing that a number without a provenance is
> worthless should show its own.

**It does not mean seasonal drift should be ignored.** A model whose input
distribution moves 17 °C between October and January genuinely may degrade. The
question the detector cannot currently answer is whether the *model* got worse,
which is why `performance_drift` exists and why the retrain verdict weighs it
separately.

**It does mean the feature-drift thresholds are not fit for weather as shipped.**
On the strength of this I would not act on a feature-drift alert on a temperature
column without checking the performance section first.

## What I would change, and why it is not changed here

The obvious fix — raise `psi_alert` until D and G go quiet — is the wrong one to
make from seven windows at one location. It would be tuning a threshold to a
sample of size seven and calling it calibration, which is the same error this
page is criticising, run in the opposite direction.

The changes worth making, in order:

1. **Compare like windows with like.** Require reference and current to be the
   same length, or normalise PSI for window size, so a fortnight and a month are
   not scored on the same scale. This is the actual bug and it is not a threshold
   question.
2. **Season-match the reference.** Compare October to last October, not to
   whatever the previous window happened to be. B shows this works.
3. **Only then** re-derive thresholds, from a real demand series, across at least
   a full year, with performance drift as the label.

None of these are made here because each changes detector behaviour, and this
round's job was to measure the thing that ships, not to move it. They are written
down here rather than quietly fixed — the measurement and the change belong in
separate commits, and the measurement is the part that has evidence behind it.

## Reproducing

```bash
uv run python scripts/drift_eval_real_weather.py
```

Fetches ~14k hourly observations from Open-Meteo (keyless, free), caches them
under `reports/` (gitignored — no data is committed), and writes
`reports/_scan/real_weather_drift.json` alongside the table above. The fetch is
the only network call; re-runs read the cache.

The raw numbers in this page came from that script on 2026-07-31. Nothing in the
table is hand-entered.

## Data attribution

Weather data by **[Open-Meteo.com](https://open-meteo.com/)**, licensed
**[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**, derived from
**ECMWF ERA5** reanalysis via the
[historical weather API](https://open-meteo.com/en/docs/historical-weather-api).

**Modified.** Every figure on this page is adapted material, not the licensed
material itself: `scripts/drift_eval_real_weather.py` takes hourly 2 m
temperature for Philadelphia and transforms it into PSI and KS statistics over
calendar windows. The raw series is not redistributed — it is cached under
gitignored `reports/`.

The licensed material is provided as-is and without warranties; see the
[licence text](https://creativecommons.org/licenses/by/4.0/legalcode) §5.

*This credit belongs here, not only in the README, because CC BY 4.0 §3(a)(1)
attaches the condition to the point where the material — or an adaptation of it —
is shared, and this page is where the derived figures are published.*
