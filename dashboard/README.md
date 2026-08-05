# dashboard

Static monitoring page over `metrics/*.json` — Vite + React + ECharts, no server,
no backend, no deploy step in this repo.

```bash
npm ci
npm run dev      # http://localhost:5173 — reads ../metrics live
npm run build    # -> dist/, a self-contained static site
```

`npm run build` copies `../metrics/*.json` into `dist/data/`, so the built site is
a directory you can serve from anywhere:

```bash
npx serve dist
```

## What it shows

v2 is a dashboard first and a writeup second. The first screen answers, without
scrolling, the three questions a cold visitor actually has — is the data real
(the pill and the banner), does it beat the baseline and by how much (the KPI
row), and what is today's drift verdict (the panel beside them). Everything
below is exploration, one anchored section per question:

| Section | Reads |
|---|---|
| Top bar: live/synthetic pill + refresh stamp | `drift.json` → `is_real`, `pipeline.json` → `generated_at_utc` |
| Provenance banner | `is_real` — see below |
| Hero KPIs (MAPE, vs baseline, horizons, ablation) | `model.json` → `metrics.*`, `ablation` |
| Today's drift verdict, first-class | `drift.json` → `verdict`, `measurable`, `reason` |
| 01 Forecast explorer (zoom/brush, "now" divider) | `forecast.json` → `history` (scored) and `forward` (live) |
| 02 Drift: monitoring stats | `monitor.json`, `drift.json` → `thresholds` |
| 02 Drift by feature / drift over time | `drift.json` → `drift.feature.columns`, `timeline.points` |
| 02 Rolling forecast error | `monitor.json` → `daily` |
| 03 Error by horizon (MAPE/MAE toggle) | `model.json` → `metrics.*.by_horizon`, `comparison.by_horizon` |
| 03 Ablation + feature importance | `model.json` → `ablation`, `feature_importance_gain_pct` |
| 04 The loop: latest run stepper | `pipeline.json` → `steps`, `status`, `seconds` |
| Provenance footer | `model.json` → `data.panel`, `drift.json` → `windows`, served model |

There is deliberately **no horizon selector on the forecast explorer**:
`forecast.json` publishes one day-ahead series, not one per horizon, and the
card says so instead of faking a control. Per-horizon error lives in section 03,
where the backtest actually measured it. The same rule governs every gap — the
artifact for a run history, KPI sparklines or forecast quantile bands does not
exist, so those mockup elements do not either; where a measurement is absent
(`measurable: false`, an empty `timeline`) the section renders the artifact's
own `reason` instead of a plausible placeholder.

`model.json` is the fifth artifact and the only one not refreshed daily: it is
written by `models.train` and changes only when a model is retrained. It carries
the walk-forward backtest, which answers "is this any good?" as none of the four
daily artifacts do.

`?theme=light` / `?theme=dark` pins the initial theme (the toggle still wins);
the default follows `prefers-color-scheme`.

## The verdict card has two shapes

`drift.json` carries `measurable`. When it is `false` the champion was trained
through the end of the available data, so nothing has arrived since that it did
not learn from, and there is no window on the far side of the training boundary
to compare against. The card then reads **"Not measurable yet"** and quotes the
artifact's own reason, instead of printing a verdict computed from windows the
model already learned. That is what once put "Retrain" over a champion trained
hours earlier.

The field is tested with `!== false` rather than for truthiness: artifacts
written before it existed have no opinion, and for those the answer is
"measured", not "unknown". `components.test.tsx` asserts all three cases.

Every chart has a **table view** toggle. That is not decoration: a tooltip must
never be the only path to a value, and two of the palette's slots sit below 3:1
contrast on the light surface, which obliges a non-colour path to the same
numbers.

## The banner is driven by the flag, not by copy

`metrics/*.json` carries `"is_real"`. While it is false, every number on the page
came from a seeded synthetic fixture, and the page says so in a red banner before
anything else renders. There is no prop or build flag that overrides it —
`ProvenanceBanner` branches on the artifact and nothing else.

To see both states without waiting for the EIA key, flip the flag on a **copy** of
the built data and serve that:

```bash
npm run build
cp -r dist /tmp/flagdemo
python - <<'PY'
import json, pathlib
for p in pathlib.Path("/tmp/flagdemo/data").glob("*.json"):
    d = json.loads(p.read_text())
    if "is_real" in d:
        d["is_real"] = True
        d["warning"] = None
        if isinstance(d.get("data"), dict):
            d["data"]["is_real"] = True
            d["data"]["kind"] = "eia_api_v2"
        p.write_text(json.dumps(d))
PY
npx serve /tmp/flagdemo    # same code, same numbers, green "Live data" banner
```

Do this on a copy only. Editing `metrics/` by hand would put a false `is_real`
into a committed artifact, which is the exact failure this whole apparatus exists
to prevent.

## Colour

The palette is declared once, in `src/styles.css`, as CSS custom properties, and
read back at render time by `useThemeTokens` — ECharts needs literal hex, and a
second copy of the palette in TypeScript would silently drift from the stylesheet
(most visibly in dark mode).

Three categorical slots (blue / orange / aqua) plus a reserved status palette,
validated in both modes against both surfaces: worst all-pairs CVD ΔE 9.2 light /
9.4 dark, worst normal-vision ΔE 24.0 light / 20.9 dark. Status colours only ever
mean good/warning/critical and always ship with an icon and a word — never colour
alone.

## Notes on the charts

- **No dual axes anywhere.** Where two measures differ by orders of magnitude
  (feature PSI vs target PSI) the axis is logarithmic, which keeps one scale and
  one truth.
- **Feature PSI is a dot plot, not bars.** A bar's length on a log axis is
  measured from the axis minimum, which would make a feature at PSI 0.02 look two
  thirds as drifted as one at 6.7. A dot encodes value by position, which survives
  any scale.
- **The live forecast keeps the forecast colour** and is separated by dash pattern
  and a shaded band. It is the same entity as the scored forecast — it just has no
  actual yet — so giving it a third hue would claim it is a different kind of
  thing.
