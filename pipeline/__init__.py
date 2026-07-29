"""The daily pipeline (M5) — one entrypoint that chains the whole loop.

`python -m pipeline.daily` runs ingest → features → score → rolling-MAE monitor
→ drift, and refreshes every file in `metrics/` plus the PNGs. It is what
`.github/workflows/daily.yml` calls, and the only thing it calls.
"""
