/**
 * The forecast explorer — actual vs forecast over time, with zoom and brush.
 *
 * Three series, two colours. `actual` and `forecast` are distinct entities and
 * take categorical slots 1 and 2. The **forward** forecast is the *same entity*
 * as `forecast` — it just has no actual to be scored against yet — so it keeps
 * the forecast hue and is separated by dash pattern, a shaded band and a "now"
 * divider rather than by a third colour. Giving it its own hue would claim it
 * is a different kind of thing.
 *
 * There is no horizon selector here on purpose: `forecast.json` publishes one
 * day-ahead series (the largest horizon within 24 h per target hour), not a
 * series per horizon. Per-horizon error lives in the model section, where the
 * backtest actually measured it. The card says so instead of faking a control.
 */

import type { EChartsOption } from "echarts";
import { useMemo, useState } from "react";

import { Chart } from "../Chart";
import { asRows, baseOption, compact, shortDateTime, timeAxis, valueAxis } from "../chartBase";
import { ChartWithTable } from "../components";
import type { Tokens } from "../theme";
import type { ForecastArtifact } from "../types";

const HOUR = 3_600_000;

/** Zoom presets over the published series — spans, not invented data. */
const RANGES = [
  { label: "48h", hours: 48 },
  { label: "7d", hours: 24 * 7 },
  { label: "all", hours: null },
] as const;

type RangeLabel = (typeof RANGES)[number]["label"];

export function ForecastChart({
  forecast,
  tokens,
  mini = false,
}: {
  forecast: ForecastArtifact;
  tokens: Tokens;
  /**
   * The overview variant: no toolbar, no table twin, no slider strip —
   * inside-zoom only, sized for the single-viewport grid. The deep-dive
   * section below renders the full version, which is where the table
   * (the non-colour path to every value) lives.
   */
  mini?: boolean;
}) {
  const [range, setRange] = useState<RangeLabel>("7d");

  const option = useMemo<EChartsOption>(() => {
    const actual = forecast.history.map((p) => [p.target_utc, p.actual_mwh ?? null]);
    const fitted = forecast.history.map((p) => [p.target_utc, p.forecast_mwh]);

    // Join the forward series to the last scored point so the line is continuous
    // and the reader can see where "scored" stops and "not yet knowable" starts.
    const last = forecast.history.at(-1);
    const forward = [
      ...(last ? [[last.target_utc, last.forecast_mwh]] : []),
      ...forecast.forward.map((p) => [p.target_utc, p.forecast_mwh]),
    ];

    const lastForward = forecast.forward.at(-1);
    const firstPoint = forecast.history[0] ?? forecast.forward[0];
    const endMs = lastForward
      ? Date.parse(lastForward.target_utc)
      : last
        ? Date.parse(last.target_utc)
        : 0;
    const spanHours = RANGES.find((r) => r.label === range)?.hours ?? null;
    const startValue =
      spanHours == null || !firstPoint
        ? firstPoint
          ? Date.parse(firstPoint.target_utc)
          : 0
        : Math.max(Date.parse(firstPoint.target_utc), endMs - spanHours * HOUR);

    return {
      ...baseOption(tokens),
      grid: mini
        ? { left: 54, right: 24, top: 38, bottom: 24,containLabel: false }
        : { left: 62, right: 24, top: 46, bottom: 78, containLabel: false },
      legend: {
        ...baseOption(tokens).legend,
        data: ["actual", "forecast (scored)", "forecast (live, no actual yet)"],
      },
      xAxis: timeAxis(tokens),
      yAxis: valueAxis(tokens, "MWh", { scale: true }),
      dataZoom: [
        {
          type: "inside",
          startValue,
          endValue: endMs,
          zoomOnMouseWheel: true,
          moveOnMouseMove: true,
        },
        ...(mini
          ? []
          : [
              {
                type: "slider" as const,
                startValue,
                endValue: endMs,
                height: 22,
                bottom: 8,
                borderColor: tokens.axis,
                backgroundColor: "transparent",
                fillerColor:
                  tokens["surface-1"].toLowerCase() === "#fcfcfb"
                    ? "rgba(11,11,11,0.06)"
                    : "rgba(255,255,255,0.08)",
                dataBackground: {
                  lineStyle: { color: tokens.axis, width: 1 },
                  areaStyle: { color: tokens.grid, opacity: 0.6 },
                },
                selectedDataBackground: {
                  lineStyle: { color: tokens["series-1"], width: 1 },
                  areaStyle: { color: tokens["series-1"], opacity: 0.12 },
                },
                moveHandleSize: 5,
                handleSize: 24,
                textStyle: { color: tokens["text-muted"], fontSize: 10 },
              },
            ]),
      ],
      tooltip: {
        ...baseOption(tokens).tooltip,
        formatter: (params: unknown) => {
          const rows = asRows(params);
          if (!rows.length) return "";
          const head = shortDateTime(rows[0].value[0]);
          const body = rows
            .filter((row) => row.value[1] !== null)
            .map(
              (row) =>
                `<div style="display:flex;gap:14px;justify-content:space-between">` +
                `<span>${row.seriesName}</span><b>${compact.format(Number(row.value[1]))} MWh</b></div>`,
            )
            .join("");
          return `<div style="font-weight:600;margin-bottom:4px">${head} UTC</div>${body}`;
        },
      },
      series: [
        {
          name: "actual",
          type: "line",
          data: actual,
          showSymbol: false,
          lineStyle: { width: 2, color: tokens["series-1"] },
          itemStyle: { color: tokens["series-1"] },
          z: 3,
        },
        {
          name: "forecast (scored)",
          type: "line",
          data: fitted,
          showSymbol: false,
          lineStyle: { width: 2, color: tokens["series-2"] },
          itemStyle: { color: tokens["series-2"] },
          z: 2,
        },
        {
          name: "forecast (live, no actual yet)",
          type: "line",
          data: forward,
          showSymbol: false,
          // Same hue as the scored forecast: same entity, different status.
          lineStyle: { width: 2, color: tokens["series-2"], type: "dashed" },
          itemStyle: { color: tokens["series-2"] },
          areaStyle: { color: tokens["series-2"], opacity: 0.09 },
          z: 2,
          // The divider between "scored" and "not yet knowable", plus the shaded
          // horizon band — both anchored on the artifact's own last scored hour.
          markLine: last
            ? {
                silent: true,
                symbol: "none",
                data: [
                  {
                    xAxis: last.target_utc,
                    lineStyle: { color: tokens["text-muted"], type: "solid", width: 1.5 },
                    label: {
                      formatter: "now",
                      position: "insideEndTop",
                      color: tokens["text-secondary"],
                      fontSize: 11,
                      backgroundColor: tokens["surface-1"],
                      padding: [2, 5],
                      borderRadius: 4,
                    },
                  },
                ],
              }
            : undefined,
          markArea:
            last && lastForward
              ? {
                  silent: true,
                  itemStyle: { color: tokens["series-2"], opacity: 0.05 },
                  label: {
                    position: "insideTop",
                    color: tokens["text-muted"],
                    fontSize: 11,
                    fontWeight: "normal",
                  },
                  data: [
                    [
                      {
                        xAxis: last.target_utc,
                        // The mini panel is too narrow for the full phrase.
                        name: mini ? "live" : "forecast horizon — no actual yet",
                      },
                      { xAxis: lastForward.target_utc },
                    ],
                  ],
                }
              : undefined,
        },
      ],
    };
  }, [forecast, mini, range, tokens]);

  const rows = [
    ...forecast.history.map((p) => ({ ...p, kind: "scored" as const })),
    ...forecast.forward.map((p) => ({ ...p, kind: "live" as const })),
  ].slice(-400);

  if (mini) {
    return (
      <Chart
        option={option}
        className="chart chart-mini"
        label="Line chart of actual demand against the day-ahead forecast, with the live forecast dashed and shaded at the right edge. The forecast section below has the full explorable version with a table view."
      />
    );
  }

  return (
    <>
      <div className="chart-toolbar">
        <span className="mono-note">window</span>
        <div className="seg" role="group" aria-label="Time window">
          {RANGES.map((r) => (
            <button
              key={r.label}
              type="button"
              aria-pressed={range === r.label}
              onClick={() => setRange(r.label)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <ChartWithTable
        caption="Day-ahead forecast against the actual demand that later arrived, plus the live forecast."
        chart={
          <Chart
            option={option}
            className="chart chart-zoomable"
            label="Line chart of actual demand against the day-ahead forecast, with a zoom slider, a divider at the last scored hour, and the live forecast dashed and shaded to its right."
          />
        }
        rows={rows}
        columns={[
          { key: "t", label: "Target (UTC)", render: (r) => shortDateTime(r.target_utc) },
          { key: "k", label: "Kind", render: (r) => r.kind },
          {
            key: "a",
            label: "Actual (MWh)",
            render: (r) => (r.actual_mwh == null ? "—" : compact.format(r.actual_mwh)),
          },
          { key: "f", label: "Forecast (MWh)", render: (r) => compact.format(r.forecast_mwh) },
          {
            key: "e",
            label: "Error (MWh)",
            render: (r) => (r.error_mwh == null ? "—" : compact.format(r.error_mwh)),
          },
        ]}
      />
    </>
  );
}
