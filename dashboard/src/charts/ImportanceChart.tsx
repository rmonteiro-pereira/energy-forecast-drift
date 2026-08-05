/**
 * Where the model's decisions come from — LightGBM gain share per feature.
 *
 * Horizontal bars on a linear percent axis (values span one order of
 * magnitude, so bars are honest here, unlike the log-scale PSI plot). One hue:
 * a single series needs no legend, and darkening by value would double-encode
 * what position already says. Feature names are set in mono because they are
 * column names, not prose.
 */

import type { EChartsOption } from "echarts";
import { useMemo } from "react";

import { Chart } from "../Chart";
import { AXIS_FONT, baseOption, precise } from "../chartBase";
import { ChartWithTable } from "../components";
import type { Tokens } from "../theme";
import type { ModelArtifact } from "../types";

export function ImportanceChart({ model, tokens }: { model: ModelArtifact; tokens: Tokens }) {
  const rows = model.feature_importance_gain_pct ?? [];

  const option = useMemo<EChartsOption>(() => {
    // ECharts draws a category y-axis bottom-up, so reverse for biggest-on-top.
    const ordered = [...rows].reverse();

    return {
      ...baseOption(tokens),
      legend: { show: false },
      grid: { left: 232, right: 56, top: 12, bottom: 40, containLabel: false },
      xAxis: {
        type: "value",
        name: "gain share (%)",
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: tokens["text-muted"], fontSize: AXIS_FONT },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: tokens["text-muted"], fontSize: AXIS_FONT },
        splitLine: { lineStyle: { color: tokens.grid, width: 1, type: "solid" } },
      },
      yAxis: {
        type: "category",
        data: ordered.map((r) => r.feature),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: tokens["text-muted"],
          fontSize: AXIS_FONT,
          fontFamily: '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          width: 218,
          overflow: "truncate",
        },
      },
      tooltip: {
        ...baseOption(tokens).tooltip,
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { name: string; value: number };
          return (
            `<div style="font-weight:600;margin-bottom:4px">${p.name}</div>` +
            `<div>gain share <b>${precise.format(p.value)}%</b></div>`
          );
        },
      },
      series: [
        {
          type: "bar",
          data: ordered.map((r) => r.gain_pct),
          itemStyle: { color: tokens["series-1"], borderRadius: [0, 4, 4, 0] },
          barMaxWidth: 14,
          label: {
            show: true,
            position: "right",
            distance: 6,
            fontSize: 11,
            color: tokens["text-secondary"],
            formatter: (p: unknown) => `${precise.format(Number((p as { value: number }).value))}%`,
          },
        },
      ],
    };
  }, [rows, tokens]);

  if (!rows.length) return <p className="card-note">No feature importances in this artifact.</p>;

  return (
    <ChartWithTable
      caption="LightGBM gain share per feature, as published by the training run."
      chart={
        <Chart
          option={option}
          className="chart chart-tall"
          label="Horizontal bar chart of gain share per model feature, largest first."
        />
      }
      rows={rows}
      columns={[
        { key: "f", label: "Feature", render: (r) => <code>{r.feature}</code> },
        { key: "g", label: "Gain share (%)", render: (r) => precise.format(r.gain_pct) },
      ]}
    />
  );
}
