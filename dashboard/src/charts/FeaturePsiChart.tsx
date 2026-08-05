/**
 * PSI per model input, right now.
 *
 * **Dots, not bars, and here is why.** PSI across these features spans three
 * orders of magnitude (0.02 to 6.7), which forces a log axis — and a bar on a
 * log axis is a lie: its length is measured from the axis minimum, so a feature
 * at PSI 0.02 gets a bar two thirds as long as one at 6.7. Bar length must be
 * proportional to the value or it must not be drawn. A dot encodes the value by
 * *position* only, which stays honest under any scale, so that is what this
 * uses, with a hairline rule per row to carry the eye from the label.
 *
 * One colour for every dot: darkening by value would double-encode magnitude the
 * chart already shows. The free channel goes to the one distinction that is not
 * in the position — deterministic calendar columns, drawn in muted ink because
 * they are reported but excluded from the verdict.
 */

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { Chart } from "../Chart";
import { AXIS_FONT, baseOption, psiFormat, verticalThresholdLine } from "../chartBase";
import { ChartWithTable, severityLabel } from "../components";
import type { Tokens } from "../theme";
import type { DriftArtifact } from "../types";

// The design matrix has 20 columns; all of them fit, and cutting the tail would
// hide exactly the deterministic calendar rows the note below is about.
const MAX_ROWS = 20;
const FLOOR = 0.001;

export function FeaturePsiChart({ drift, tokens }: { drift: DriftArtifact; tokens: Tokens }) {
  const columns = (drift.drift.feature?.columns ?? []).slice(0, MAX_ROWS);

  const option = useMemo<EChartsOption>(() => {
    // ECharts draws a category y-axis bottom-up, so reverse for worst-on-top.
    const ordered = [...columns].reverse();
    const { psi_warn: warn, psi_alert: alert } = drift.thresholds;

    return {
      ...baseOption(tokens),
      legend: { show: false },
      grid: { left: 224, right: 74, top: 20, bottom: 46, containLabel: false },
      xAxis: {
        type: "log",
        min: FLOOR,
        name: "PSI (log scale)",
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: tokens["text-muted"], fontSize: AXIS_FONT },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: tokens["text-muted"], fontSize: AXIS_FONT },
        splitLine: { lineStyle: { color: tokens.grid, width: 1, type: "solid" } },
      },
      yAxis: {
        type: "category",
        data: ordered.map((c) => c.column),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: tokens["text-muted"],
          fontSize: AXIS_FONT,
          fontFamily: '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          width: 210,
          overflow: "truncate",
        },
        // The hairline that carries the eye from the label to the dot.
        splitLine: { show: true, lineStyle: { color: tokens.grid, width: 1, type: "solid" } },
      },
      tooltip: {
        ...baseOption(tokens).tooltip,
        trigger: "item",
        formatter: (params: unknown) => {
          const column = ordered[(params as { dataIndex: number }).dataIndex];
          const excluded = column.deterministic
            ? `<div style="color:${tokens["text-muted"]};margin-top:4px">deterministic calendar column — reported, excluded from the verdict</div>`
            : "";
          return (
            `<div style="font-weight:600;margin-bottom:4px">${column.column}</div>` +
            `<div>PSI <b>${psiFormat.format(column.psi.psi)}</b> · ${severityLabel(column.severity)}</div>` +
            `<div style="color:${tokens["text-muted"]}">KS p = ${column.ks.p_value.toExponential(2)}</div>` +
            excluded
          );
        },
      },
      series: [
        {
          type: "scatter",
          data: ordered.map((column, index) => ({
            value: [Math.max(column.psi.psi, FLOOR), index],
            itemStyle: {
              color: column.deterministic ? tokens["text-muted"] : tokens["series-1"],
              opacity: column.deterministic ? 0.5 : 1,
              // 2px surface ring so overlapping dots stay countable.
              borderColor: tokens["surface-1"],
              borderWidth: 2,
            },
          })),
          symbolSize: 11,
          // Direct labels: the value is readable without landing on the dot.
          label: {
            show: true,
            position: "right",
            distance: 8,
            fontSize: 11,
            color: tokens["text-secondary"],
            formatter: (p: unknown) =>
              psiFormat.format(Number((p as { value: [number, number] }).value[0])),
          },
          labelLayout: { hideOverlap: true },
          markLine: {
            silent: true,
            symbol: "none",
            data: [
              verticalThresholdLine(tokens, warn, `warn ${warn}`, tokens["status-warning"]),
              verticalThresholdLine(tokens, alert, `alert ${alert}`, tokens["status-critical"]),
            ],
          },
        },
      ],
    };
  }, [columns, drift.thresholds, tokens]);

  if (!columns.length) return <p className="card-note">No feature columns were scored.</p>;

  return (
    <ChartWithTable
      caption="Population Stability Index per model input for the current window against the reference."
      chart={
        <Chart
          option={option}
          className="chart chart-tall"
          label="Dot plot of PSI per model input on a log scale, against the warn and alert thresholds."
        />
      }
      rows={columns}
      columns={[
        { key: "c", label: "Feature", render: (r) => <code>{r.column}</code> },
        { key: "p", label: "PSI", render: (r) => psiFormat.format(r.psi.psi) },
        { key: "k", label: "KS p", render: (r) => r.ks.p_value.toExponential(2) },
        { key: "s", label: "Severity", render: (r) => severityLabel(r.severity) },
        {
          key: "v",
          label: "Counts toward verdict",
          render: (r) => (r.deterministic ? "no (calendar)" : "yes"),
        },
      ]}
    />
  );
}
