# 0003 — Implement PSI and KS rather than import them

**Status:** Accepted · **Date:** 2026-07

## Context

The drift suite needs a distribution-distance measure (PSI) and a two-sample
test (Kolmogorov–Smirnov). Both exist in libraries: `scipy.stats.ks_2samp` is one
call, and PSI ships inside several drift packages.

Both are also three-line formulas wrapped in a lot of edge cases, and the edge
cases are where drift detectors quietly stop working:

- a bin with zero reference mass makes PSI infinite;
- a constant column collapses the quantile edges to a single value;
- a 30-row window makes every statistic significant;
- quantile-binning a categorical column such as `hour` merges levels arbitrarily
  and hides exactly the shift that matters — a new weekly shape.

## Decision

Write both out in `drift/stats.py`, with every degenerate case named and handled:

- bin edges come from the **reference** quantiles, opened to ±∞ so current values
  outside the reference range land in the extreme bins instead of being dropped;
- zero shares are **floored at `EPSILON = 1e-6`, not skipped** — a bin that held
  8% of the reference and 0% of the current window is the event PSI exists to
  catch, and skipping it would report *less* drift the worse the drift got;
- columns with ≤24 distinct reference values are binned categorically, with an
  `<unseen>` catch-all;
- `D` is computed exactly from the pooled order statistics; the p-value uses the
  standard asymptotic form, which needs no scipy at runtime.

Correctness is pinned by tests against `scipy.stats.ks_2samp` — to 1e-12 on the
statistic and 1e-3 on the p-value — plus a two-bin PSI worked out by hand. scipy
is a *test* dependency only.

## Rejected alternatives

**Import `scipy.stats.ks_2samp` and a PSI helper.** Rejected because it hides
every decision above behind a number nobody can defend in review. When the alarm
fires at 3am the question is "why is this 6.7", and "the library said so" is not
an answer. It would also have made scipy a runtime dependency of a container
whose only other need is LightGBM.

**Use Evidently as the sole detector.** Rejected as the *primary*, kept as a
second opinion. Evidently is good and it runs alongside — but it makes its own
binning and thresholding choices, and a monitor whose behaviour you cannot
predict from reading your own code is not a monitor you can tune. It is recorded
in the artifact, deliberately **not** wired into the retrain trigger, and it is
an optional dependency: a missing Evidently yields `"status": "unavailable"`,
never a failed pipeline.

**Use only KS, or only PSI.** Rejected because they answer different questions.
KS gives a significance statement that becomes trivially significant at thousands
of rows; PSI gives an effect size with no significance attached. Reporting both,
and triggering on PSI while recording KS, keeps the size and the confidence
separate.

## Consequences

- ~260 lines to maintain that a dependency would have provided.
- The behaviour on every degenerate input is a documented choice with a test,
  rather than whatever the library happened to do.
- No scipy at runtime.
- **A genuine limitation is now visible rather than hidden:** PSI is scale-free
  relative to the reference spread, so heavily smoothed features
  (`demand_roll_mean_168h`) show enormous PSI for level moves that are small in
  MW. Narrow reference bins make small absolute moves look catastrophic. That is
  a property of PSI, not a bug — and it is why the section verdict uses the
  *share* of drifted columns rather than the maximum, and why a distribution
  alert alone never triggers a retrain (see [0004](0004-retrain-policy-not-threshold.md)).

## What would reverse this

If the edge-case handling ever needed to diverge meaningfully from the standard
definitions to keep the alarm useful, that would be a signal the measure is wrong
for this data rather than that the implementation needs another special case —
and the right move would be to change the measure (Wasserstein, or a
population-level test on the residuals) rather than to keep patching PSI.

Equally: if the hand-written version and Evidently ever disagree materially, that
is a bug in ours until proven otherwise, and the disagreement is the reason
Evidently is kept in the artifact.
