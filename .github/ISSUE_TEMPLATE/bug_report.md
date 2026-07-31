---
name: Bug report
about: Something behaves differently from what the docs say
title: ""
labels: bug
---

## What you ran

```bash
# the exact command
```

## What happened

<!-- Paste the real output, including the traceback. Trimmed is fine; retyped is not. -->

## What you expected

## Environment

- OS:
- Python (`uv run python -V`):
- Node, if the dashboard is involved (`node -v`):
- Commit (`git rev-parse --short HEAD`):

## Checked

- [ ] This is reproducible from a clean clone (`uv sync --extra dev`).
- [ ] It is not the documented no-API-key behaviour — every number in this repo
      is a seeded synthetic fixture, and `"is_real": false` in `metrics/*.json`
      is expected, not a bug. See the README banner.
