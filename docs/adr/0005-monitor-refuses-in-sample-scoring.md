# 0005 — Refuse to monitor with a model that trained on the monitoring windows

**Status:** Accepted · **Date:** 2026-07 · **This records a bug that shipped and was caught.**

## Context

The monitor scores two windows — a reference window and a current window — and
compares the errors. The natural implementation is to score them with the model
that is actually being served, since that is the model whose behaviour you care
about.

That is what the first implementation did, and it was wrong.

`models.train` refits the champion on **all** available history before
registering it, so by the time a version carries the `@champion` alias it has
already seen both monitoring windows. Scoring them with it gives *in-sample*
errors. On the fixture the gap was stark:

| | MAE |
|---|---|
| champion scoring the reference window it trained on | ~1,015 MWh |
| the same model scoring data it had not seen | ~2,657 MWh |

*(Both fixture-derived, quoted only as the symptom.)*

A reference baseline 2.6× better than reality means **every future window looks
catastrophic forever**, against a number that was never achievable. The drift
monitor would have reported permanent, worsening degradation on a perfectly
healthy model.

Nothing failed. No test broke. It was found by noticing that a reference MAE
looked implausibly good.

## Decision

Training runs stamp the model with `train_data_end_utc`. The monitor uses the
registry champion **only** when that tag proves its training data ended before
the reference window opens:

```python
if trained_to is None:
    return None, {
        "source": "fitted_on_train_window",
        "reason": "the champion does not record `train_data_end_utc`, ...",
    }
if pd.Timestamp(trained_to) >= reference_start:
    return None, {
        "source": "fitted_on_train_window",
        "reason": f"... covers the reference window opening at ...; "
        "scoring it there would be in-sample",
    }
```

Otherwise it fits its own booster on the train slice and **records why, in the
artifact**. A missing tag counts as ineligible: unknown is not safe.

Because of this the artifacts distinguish two models and never conflate them:
`served_model` (what `/forecast` returns) and `monitoring_model` (what scored the
windows the alarm reads).

## Rejected alternatives

**Compare current-window error to a fixed historical constant.** Rejected: it
answers "is the model worse than it was in July" rather than "is the model worse
than it should be now", and it decays silently as the series drifts.

**Always fit a fresh monitoring booster and never use the champion.** Simpler,
and it is what happens in practice today. Rejected as the *rule* because when the
champion genuinely is out of sample it is the right thing to score with — it is
the model actually serving traffic, and its errors are the ones users experience.
The tag check keeps that path open instead of closing it permanently.

**Hold out a window at training time and never train on it.** Correct in
principle, and rejected only because the champion is deliberately refit on all
history to serve the best available model. Permanently sacrificing the most
recent weeks — the most informative data for a load forecaster — to reserve a
monitoring window costs more than fitting a second small booster does.

**Tune the alert thresholds so the in-sample baseline stopped firing.** Briefly
considered and rejected outright. It would have hidden the symptom of a wrong
baseline behind a number chosen to make the wrong baseline look fine.

## Consequences

- The monitor usually fits its own booster, which costs a few seconds per run.
- Artifacts carry two model blocks, which is more to explain but prevents the
  worse outcome of conflating them.
- A model registered *without* the tag is ineligible, so an older registry entry
  silently stops being used for monitoring. This is recorded in the artifact's
  `reason` field rather than being silent.

## What would reverse this

If training ever stops refitting on all history — for example if a proper
held-out evaluation window became part of the training protocol — the champion
would be out of sample by construction and the eligibility check would become
dead code. It should then be deleted rather than left as reassuring noise.

The tag itself should not be removed under any circumstance: the check treats a
missing tag as ineligible precisely so that deleting it degrades safely instead
of silently restoring the bug.
