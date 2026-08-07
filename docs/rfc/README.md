# Requests for comment

Where an ADR records a decision that was already taken, an RFC records a design
being **attacked before it is built** — the committee that shaped it, the rounds
that tried to refute it, and the round that said stop.

| | |
|---|---|
| [`rfc-foundation-vs-gbm.md`](rfc-foundation-vs-gbm.md) | Zero-shot foundation models against the GBM, on the same walk-forward folds. v4 — four versions, three adversarial rounds, 160 findings. |
| [`DECISIONS-foundation-vs-gbm.md`](DECISIONS-foundation-vs-gbm.md) | The 29 decisions those rounds forced, each with a reversal criterion that is a **test**, not an opinion. |

## Why they are in the repository

They are the provenance of a diff that changes `models/backtest.py`,
`models/train.py` and `features/build.py` — three files with mutation testing on
two of them and a leakage guarantee on all three. A reader who wants to know why
`compare()` now refuses divergent fold sets, or why the cost lines are never
summed, should not have to reconstruct it from commit messages.

Both documents record what was **wrong** as much as what was decided, including
in the documents themselves: `§0` lists defects in already-published code, and
the phase sections record the gates that were green on the defect they existed
to catch until they were run. That is the part that is worth keeping.

## A note on the transcripts

The prose is English. The fenced blocks are **verbatim records of what a run
printed** and are left exactly as they came out, including Portuguese labels from
the probe scripts that produced them. Translating a transcript would falsify it,
and this repository already draws that line: *"Transcripts are exempt — they are
dated records of what a run printed"* (`tests/test_doc_claims.py:3-9`).

## The stop rule

The RFC stopped at v4 because every blocker in the last round had the same shape
— a gate verified by reasoning rather than by execution — and therefore the same
fix: build the canary and watch it fail. Reviewing the document had started
yielding less than running the gate.

That was the right call and the implementation proved it the hard way. Every
phase after the stop found defects no further reading would have surfaced,
including in gates the RFC had just finished specifying, and including a finding
the last round had wrongly refuted.

The last phase made the point twice over. The Chronos adapter — specified,
reviewed across three adversarial rounds, and covered by tests — **did not work**:
it called the library with a keyword argument that library had renamed, and the
first line of it ever executed with torch installed raised `TypeError`. In the
same phase, a gate whose only falsifiable condition had spent its whole life in
an environment where it could not fail was finally put in one where it could.

## What is not in here

The verdict. `metrics/foundation.json` needs `EIA_API_KEY` and a filled lake, and
the lane is written so that the file is **real or absent** — enforced by a test
and again by the runner, which refuses to write it from a fixture. `§4.6` records
that boundary rather than blurring it, and `docs/BLOCKED.md` has the command.
