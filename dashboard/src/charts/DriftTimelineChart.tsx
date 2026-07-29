/**
 * Drift over time — PSI of a trailing 7-day window against the reference.
 *
 * Three series (worst feature, target, prediction) on **one** axis, which needs
 * a note: the feature PSI runs one to two orders of magnitude above the other
 * two, because PSI is scale-free relative to the *reference spread* and the
 * smoothed rolling features have a very narrow one. A second y-axis would
 * "solve" that by inventing an alignment between two scales — the single worst
 * chart mistake there is. A log axis keeps one scale and one truth, so that is
 * what this uses, and the axis says so.
 *
 * The two PSI thresholds are `markLine`s in status colours, which is what makes
 * the log axis readable: the eye reads distance from the alert line, not the
 * absolute height.
 */

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { Chart } from "../Chart";
import {
  asRows,
  baseOption,
  psiFormat,
  shortDay,
  thresholdLine,
  timeAxis,
  valueAxis,
} from "../chartBase";
import { ChartWithTable } from "../components";
import type { Tokens } from "../theme";
import type { DriftArtifact } from "../types";

export function DriftTimelineChart({ drift, tokens }: { drift: DriftArtifact; tokens: Tokens }) {
  const points = drift.timeline?.points ?? [];

  const option = useMemo<EChartsOption>(() => {
    const { psi_warn: warn, psi_alert: alert } = drift.thresholds;
    const line = (name: string, color: string, pick: (p: (typeof points)[number]) => number | null) => ({
      name,
      type: "line" as const,
      data: points.map((p) => [p.day_utc, pick(p)]),
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 2, color },
      itemStyle: { color },
    });

    return {
      ...baseOption(tokens),
      legend: {
        ...baseOption(tokens).legend,
        data: ["worst feature", "target (demand)", "prediction (forecast)"],
      },
      xAxis: timeAxis(tokens),
      yAxis: valueAxis(tokens, "PSI (log scale)", { type: "log", min: 0.001 }),
      tooltip: {
        ...baseOption(tokens).tooltip,
        formatter: (params: unknown) => {
          const rows = asRows(params);
          if (!rows.length) return "";
          const point = points.find((p) => p.day_utc === rows[0].value[0]);
          const body = rows
            .filter((row) => row.value[1] != null)
            .map(
              (row) =>
                `<div style="display:flex;gap:14px;justify-content:space-between">` +
                `<span>${row.seriesName}</span><b>${psiFormat.format(Number(row.value[1]))}</b></div>`,
            )
            .join("");
          const extra = point?.feature_max_column
            ? `<div style="color:${tokens["text-muted"]};margin-top:4px">worst feature: ${point.feature_max_column}</div>`
            : "";
          return `<div style="font-weight:600;margin-bottom:4px">${shortDay(rows[0].value[0])}</div>${body}${extra}`;
        },
      },
      series: [
        {
          ...line("worst feature", tokens["series-1"], (p) => p.feature_max_psi),
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              // Staggered: warn sits just under alert, so their labels would
              // otherwise overprint on a log axis.
              thresholdLine(tokens, warn, `warn ${warn}`, tokens["status-warning"], false),
              thresholdLine(tokens, alert, `alert ${alert}`, tokens["status-critical"], true),
            ],
          },
        },
        line("target (demand)", tokens["series-2"], (p) => p.target_psi),
        line("prediction (forecast)", tokens["series-3"], (p) => p.prediction_psi),
      ],
    };
  }, [drift.thresholds, points, tokens]);

  if (!points.length) {
    return (
      <p className="card-note">
        No drift timeline in this artifact — it accumulates once the daily pipeline has run.
      </p>
    );
  }

  return (
    <ChartWithTable
      caption="Population Stability Index of a trailing 7-day window against the reference window, per day."
      chart={
        <Chart
          option={option}
          label="Log-scale line chart of PSI over time for the worst feature, the target and the prediction, against the warn and alert thresholds."
        />
      }
      rows={points}
      columns={[
        { key: "d", label: "Day (UTC)", render: (r) => shortDay(r.day_utc) },
        { key: "w", label: "Window", render: (r) => r.window },
        {
          key: "f",
          label: "Worst feature PSI",
          render: (r) => (r.feature_max_psi == null ? "—" : psiFormat.format(r.feature_max_psi)),
        },
        { key: "c", label: "Which feature", render: (r) => r.feature_max_column ?? "—" },
        { key: "t", label: "Target PSI", render: (r) => psiFormat.format(r.target_psi) },
        { key: "p", label: "Prediction PSI", render: (r) => psiFormat.format(r.prediction_psi) },
      ]}
    />
  );
}
