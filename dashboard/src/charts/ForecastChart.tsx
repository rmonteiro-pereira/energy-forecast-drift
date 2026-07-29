/**
 * Forecast vs actual — change over time, so: lines on one shared value axis.
 *
 * Three series, two colours. `actual` and `forecast` are distinct entities and
 * take categorical slots 1 and 2. The **forward** forecast is the *same entity*
 * as `forecast` — it just has no actual to be scored against yet — so it keeps
 * the forecast hue and is separated by dash pattern and by a shaded band rather
 * than by a third colour. Giving it its own hue would claim it is a different
 * kind of thing.
 */

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { Chart } from "../Chart";
import { asRows, baseOption, compact, shortDateTime, timeAxis, valueAxis } from "../chartBase";
import { ChartWithTable } from "../components";
import type { Tokens } from "../theme";
import type { ForecastArtifact } from "../types";

export function ForecastChart({
  forecast,
  tokens,
}: {
  forecast: ForecastArtifact;
  tokens: Tokens;
}) {
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

    return {
      ...baseOption(tokens),
      legend: {
        ...baseOption(tokens).legend,
        data: ["actual", "forecast (scored)", "forecast (live, no actual yet)"],
      },
      xAxis: timeAxis(tokens),
      yAxis: valueAxis(tokens, "MWh", { scale: true }),
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
        },
      ],
    };
  }, [forecast, tokens]);

  const rows = [
    ...forecast.history.map((p) => ({ ...p, kind: "scored" as const })),
    ...forecast.forward.map((p) => ({ ...p, kind: "live" as const })),
  ].slice(-400);

  return (
    <ChartWithTable
      caption="Day-ahead forecast against the actual demand that later arrived, plus the live forecast."
      chart={
        <Chart
          option={option}
          label="Line chart of actual demand against the day-ahead forecast, with the live forecast dashed at the right edge."
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
  );
}
