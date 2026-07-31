# 0004 — Make the retrain trigger a policy, not a threshold

**Status:** Accepted · **Date:** 2026-07

## Context

The suite computes four drift signals: feature, target, prediction and
performance. Something has to turn them into a decision.

The obvious implementation is `if psi > 0.2: retrain()`. On this data that fires
constantly — the fixture carries a real annual cycle, so a 28-day reference
window against a 14-day current window spans different months and the temperature
and rolling-level features genuinely move. Eight of fourteen eligible features sit
above PSI 0.2 on a completely healthy run.

Retraining on every excursion is not merely noisy. It retrains on a window that
may be too short to have learned the new regime, which can produce a champion
*worse* than the one it replaced — and then the next excursion retrains again
from that worse baseline.

## Decision

A five-rule policy returning a **structured verdict**, not a bool:

| rule | condition | verdict |
|---|---|---|
| R1 | performance alerts | **retrain** — measured harm, nothing else needed |
| R2 | a distribution signal alerts **and** performance warns | **retrain** — cause plus visible effect |
| R3 | two or more distribution signals alert | **retrain** — regime change, act before the errors confirm it |
| R4 | anything else non-`ok` | **watch** — charted, not acted on |
| R5 | all four `ok` | **healthy** |

`RetrainVerdict` carries `should_retrain`, the rule that fired, a rationale, a
per-signal map, and every reason as a metric/threshold/value triple. A pipeline
branches on one field; a human audits the rest.

Two supporting decisions fall out of the same reasoning:

- **Deterministic calendar features are reported but never vote.** `month` scores
  PSI ≈ 7 on every healthy run because the windows span different months, and
  `is_holiday` swings on the luck of the calendar. Letting a deterministic
  function of the timestamp drive the alarm means firing daily. They stay in the
  artifact — useful for sanity-checking the window geometry — and are excluded
  from the section verdict, with `columns_excluded_deterministic` recorded.
- **Section severity uses the share of drifted columns, not the maximum.** One
  hypersensitive smoothed feature should not outvote thirteen quiet ones (see
  [0003](0003-own-psi-and-ks-implementations.md) on why PSI is hypersensitive
  there).

## Rejected alternatives

**A single PSI threshold.** Rejected as above: it fires every day on healthy
data, which trains people to ignore the alarm. A detector that always fires is
worse than one that never does, because the second is obviously broken.

**Trigger on performance only.** Tempting — it is the only signal that proves
harm. Rejected because it is also the slowest: performance drift needs actuals,
and actuals arrive late. By the time rolling MAE moves, the bad forecasts have
already been served. R2 and R3 exist to act on a cause with corroboration, before
the errors confirm it.

**Return a bare `bool`.** Rejected because the interesting question in an
incident is never "should I retrain" but "why does it think so". A bool discards
exactly the information needed to decide whether to trust it.

**Auto-retrain and auto-promote on the verdict.** Rejected. The verdict feeds a
decision, not a deploy. Promotion to `@champion` stays gated on beating the
seasonal naive on identical folds — a model that loses to a one-line baseline
does not get promoted no matter what the drift monitor thinks.

## Consequences

- The common verdict on healthy data is **watch**, not **healthy**, because
  feature drift genuinely alerts. That reads as alarming at a glance and needs
  the rationale next to it — a real UX cost, mitigated on the dashboard by
  putting the rationale directly under the verdict.
- Five rules is more to explain than one threshold.
- The thresholds are still thresholds; the policy governs how they *combine*, and
  every one is overridable from the environment (`DRIFT_*`) and recorded in the
  artifact so a reader can see what was in force.

## What would reverse this

Real data. The whole rule set is calibrated against a fixture whose drift
behaviour is an artefact of how it was generated. Once real PJM demand is
flowing, the first genuine drift episode is the test: if R1–R3 fire on it, the
policy is right; if it slips through to R4 and the errors blow out unattended,
the thresholds or the rules need to change — and that episode, not this table,
becomes the justification.

Specifically, if performance drift turns out to lead rather than lag on this
series, R2 and R3 lose their reason to exist and the policy should collapse
toward R1.
