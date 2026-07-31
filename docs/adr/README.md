# Architecture decision records

Short records of the decisions that shaped this repository — each one stating the
alternative that was rejected and **the condition that would reverse it**.

A decision without a reversal condition is a preference. Writing down what would
change my mind is the part that makes these useful to someone inheriting the
code, because it tells them when the reasoning has expired.

| # | Decision | Status |
|---|---|---|
| [0001](0001-synthetic-fixture-instead-of-waiting.md) | Ship a labelled synthetic fixture rather than wait for the API key | Accepted |
| [0002](0002-scoped-type-checking.md) | Type-check strictly in the logic core, loosely in the dataframe plumbing | Accepted |
| [0003](0003-own-psi-and-ks-implementations.md) | Implement PSI and KS rather than import them | Accepted |
| [0004](0004-retrain-policy-not-threshold.md) | Make the retrain trigger a policy, not a threshold | Accepted |
| [0005](0005-monitor-refuses-in-sample-scoring.md) | Refuse to monitor with a model that trained on the monitoring windows | Accepted |
| [0006](0006-dormant-workflow-instead-of-red.md) | Let the daily workflow go dormant rather than fail red | Accepted |
| [0007](0007-mutation-testing-scoped-not-global.md) | Mutation-test the two places a green suite would be most misleading | Accepted |

## Format

Each record is deliberately short:

- **Context** — what was true when the decision was made.
- **Decision** — what was chosen.
- **Rejected alternatives** — what else was on the table, and why it lost. This
  is the section that matters.
- **Consequences** — what this costs, stated honestly.
- **What would reverse this** — the observation that should make someone redo it.
