/**
 * The rolling-MAE monitor — is the model getting worse, and since when.
 *
 * Daily MAE as thin bars (magnitude per day) with the rolling mean as a line on
 * top: one value axis, two marks, no second scale. The reference level and the
 * retrain line are `markLine`s — dashed, because here dashing genuinely means
 * "threshold" — and the current window is shaded so the split the drift verdict
 * is computed across is visible rather than implied.
 */

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { Chart } from "../Chart";
import {
  asRows,
  baseOption,
  compact,
  precise,
  shortDay,
  thresholdLine,
  timeAxis,
  valueAxis,
} from "../chartBase";
import { ChartWithTable } from "../components";
import type { Tokens } from "../theme";
import type { MonitorArtifact } from "../types";

export function MaeTrendChart({
  monitor,
  tokens,
  mini = false,
}: {
  monitor: MonitorArtifact;
  tokens: Tokens;
  /** Overview variant: no table twin, grid-sized. The drift section keeps the full one. */
  mini?: boolean;
}) {
  const option = useMemo<EChartsOption>(() => {
    const days = monitor.daily;
    const current = days.filter((d) => d.window === "current");
    const reference = monitor.reference.mae;

    const markLines = [
      ...(reference != null
        ? [
            thresholdLine(
              tokens,
              reference,
              `reference ${compact.format(reference)}`,
              tokens.axis,
              false,
            ),
          ]
        : []),
      ...(monitor.alert_line_mae != null
        ? [
            thresholdLine(
              tokens,
              monitor.alert_line_mae,
              `retrain line ${compact.format(monitor.alert_line_mae)}`,
              tokens["status-critical"],
            ),
          ]
        : []),
    ];

    return {
      ...baseOption(tokens),
      grid: mini
        ? { left: 50, right: 8, top: 36, bottom: 24, containLabel: false }
        : baseOption(tokens).grid,
      legend: { ...baseOption(tokens).legend, data: ["daily MAE", "rolling mean"] },
      xAxis: timeAxis(tokens),
      yAxis: valueAxis(tokens, "MAE (MWh)", { min: 0 }),
      tooltip: {
        ...baseOption(tokens).tooltip,
        formatter: (params: unknown) => {
          const rows = asRows(params);
          if (!rows.length) return "";
          const day = days.find((d) => d.day_utc === rows[0].value[0]);
          const body = rows
            .map(
              (row) =>
                `<div style="display:flex;gap:14px;justify-content:space-between">` +
                `<span>${row.seriesName}</span><b>${compact.format(Number(row.value[1]))} MWh</b></div>`,
            )
            .join("");
          const extra = day
            ? `<div style="color:${tokens["text-muted"]};margin-top:4px">${day.window} window · MAPE ${precise.format(day.mape_pct)}%</div>`
            : "";
          return `<div style="font-weight:600;margin-bottom:4px">${shortDay(rows[0].value[0])}</div>${body}${extra}`;
        },
      },
      series: [
        {
          name: "daily MAE",
          type: "bar",
          data: days.map((d) => [d.day_utc, d.mae]),
          // 4px rounded data-end anchored to the baseline.
          itemStyle: { color: tokens["series-1"], opacity: 0.32, borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 16,
          z: 1,
          markArea:
            current.length > 1
              ? {
                  silent: true,
                  itemStyle: { color: tokens["series-2"], opacity: 0.06 },
                  label: {
                    position: "insideTopLeft",
                    color: tokens["text-muted"],
                    fontSize: 11,
                    fontWeight: "normal",
                  },
                  data: [
                    [
                      { xAxis: current[0].day_utc, name: "current window" },
                      { xAxis: current[current.length - 1].day_utc },
                    ],
                  ],
                }
              : undefined,
        },
        {
          name: "rolling mean",
          type: "line",
          data: days.map((d) => [d.day_utc, d.mae_rolling]),
          showSymbol: false,
          lineStyle: { width: 2, color: tokens["series-2"] },
          itemStyle: { color: tokens["series-2"] },
          z: 3,
          markLine: markLines.length
            ? { silent: true, symbol: "none", data: markLines }
            : undefined,
        },
      ],
    };
  }, [mini, monitor, tokens]);

  if (mini) {
    return (
      <Chart
        option={option}
        className="chart chart-mini"
        label="Bar and line chart of daily forecast MAE against the reference level and the retrain threshold. The drift section below has the full version with a table view."
      />
    );
  }

  return (
    <ChartWithTable
      caption="Daily mean absolute error with its rolling mean, the reference level and the retrain line."
      chart={
        <Chart
          option={option}
          label="Bar and line chart of daily forecast MAE over time against the reference level and the retrain threshold."
        />
      }
      rows={monitor.daily}
      columns={[
        { key: "d", label: "Day (UTC)", render: (r) => shortDay(r.day_utc) },
        { key: "w", label: "Window", render: (r) => r.window },
        { key: "m", label: "MAE (MWh)", render: (r) => compact.format(r.mae) },
        { key: "r", label: "Rolling MAE", render: (r) => compact.format(r.mae_rolling) },
        { key: "p", label: "MAPE (%)", render: (r) => precise.format(r.mape_pct) },
        { key: "n", label: "n", render: (r) => r.n },
      ]}
    />
  );
}
