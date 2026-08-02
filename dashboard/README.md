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

The order is the argument, and it used to be wrong. The page opened on the
retrain verdict, which is the last question a first-time reader has and the
first one the author has. Someone landing cold does not know what is being forecast,
whether it works, or how it was built, and a page that answers "should the model
be retrained?" before any of those is answering into a vacuum. So:

| Section | Reads |
|---|---|
| What this is / what it runs on | `model.json` → `data`, `models.challenger` |
| Provenance banner | `is_real` — see below |
| What it delivers | `model.json` → `metrics.*`, `ablation`, `backtest` |
| How it was made, six stages | `model.json` → `backtest`, `models`, `data` |
| The forecast, against what happened | `forecast.json` → `history` (scored) and `forward` (live) |
| Retrain verdict + signal chips | `drift.json` → `verdict`, `drift.*.severity` |
| Monitoring stats | `monitor.json`, `drift.json` → `thresholds` |
| Drift over time | `drift.json` → `timeline.points` |
| Rolling forecast error | `monitor.json` → `daily` |
| Feature drift right now | `drift.json` → `drift.feature.columns` |

`model.json` is the fifth artifact and the only one not refreshed daily: it is
written by `models.train` and changes only when a model is retrained. It carries
the walk-forward backtest, which answers "is this any good?" as none of the four
daily artifacts do, and which this page did not read at all until the
sections above were added.

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
