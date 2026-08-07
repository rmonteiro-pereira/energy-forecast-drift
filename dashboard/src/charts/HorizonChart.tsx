/**
 * Model vs baseline, one pair of bars per horizon — the 24 fights the champion
 * had to win to be promoted, shown individually instead of averaged away.
 *
 * Colour follows the entity: the model keeps the forecast orange it wears in
 * the explorer above, and the baseline is deliberately neutral grey — it is
 * the reference being beaten, not a second protagonist. Legend + direct table
 * keep the identity readable without colour.
 *
 * One value axis. MAE and MAPE are different scales, so they are a toggle,
 * never two axes on one chart.
 */

import type { EChartsOption } from "echarts";
import { useMemo, useState } from "react";

import { Chart } from "../Chart";
import { AXIS_FONT, asRows, baseOption, compact, precise, valueAxis } from "../chartBase";
import { ChartWithTable, EmptyPanel } from "../components";
import type { Tokens } from "../theme";
import type { ModelArtifact } from "../types";

type Metric = "MAE" | "MAPE";

export function HorizonChart({
  model,
  tokens,
  mini = false,
}: {
  model: ModelArtifact;
  tokens: Tokens;
  /** Overview variant: MAPE only, no toolbar, no table twin, grid-sized. */
  mini?: boolean;
}) {
  const [metric, setMetric] = useState<Metric>("MAPE");

  const baseline = model.metrics.baseline.by_horizon ?? [];
  const champion = model.metrics.lightgbm.by_horizon ?? [];
  const deltas = model.metrics.comparison.by_horizon ?? [];

  const option = useMemo<EChartsOption>(() => {
    const pick = (row: { mae: number; mape_pct: number }) =>
      metric === "MAE" ? row.mae : row.mape_pct;
    const unit = metric === "MAE" ? "MWh" : "%";
    const fmt = (v: number) => (metric === "MAE" ? compact.format(v) : precise.format(v));

    return {
      ...baseOption(tokens),
      grid: mini
        ? { left: 46, right: 18, top: 36, bottom: 34, containLabel: false }
        : { left: 62, right: 24, top: 46, bottom: 44, containLabel: false },
      legend: {
        ...baseOption(tokens).legend,
        data: ["model (LightGBM)", "baseline (seasonal-naive)"],
        icon: "rect",
        itemHeight: 8,
        itemWidth: 12,
      },
      xAxis: {
        type: "category",
        name: "hours ahead",
        nameLocation: "middle",
        nameGap: 28,
        nameTextStyle: { color: tokens["text-muted"], fontSize: AXIS_FONT },
        data: champion.map((r) => String(r.horizon_h)),
        axisLine: { lineStyle: { color: tokens.axis } },
        axisTick: { show: false },
        axisLabel: { color: tokens["text-muted"], fontSize: AXIS_FONT },
      },
      yAxis: valueAxis(tokens, `${metric} (${unit})`, { min: 0 }),
      tooltip: {
        ...baseOption(tokens).tooltip,
        formatter: (params: unknown) => {
          const rows = asRows(params);
          if (!rows.length) return "";
          const index = (rows[0] as unknown as { dataIndex: number }).dataIndex;
          const delta = deltas[index];
          const body = rows
            .map(
              (row) =>
                `<div style="display:flex;gap:14px;justify-content:space-between">` +
                `<span>${row.seriesName}</span><b>${fmt(Number(row.value))} ${unit}</b></div>`,
            )
            .join("");
          const extra = delta
            ? `<div style="color:${tokens["text-muted"]};margin-top:4px">MAE delta ${precise.format(delta.mae_delta_pct)}%</div>`
            : "";
          return (
            `<div style="font-weight:600;margin-bottom:4px">${champion[index]?.horizon_h}h ahead</div>` +
            body +
            extra
          );
        },
      },
      series: [
        {
          name: "baseline (seasonal-naive)",
          type: "bar",
          data: baseline.map((r) => pick(r)),
          itemStyle: {
            color: tokens["text-muted"],
            opacity: 0.45,
            borderRadius: [4, 4, 0, 0],
          },
          barMaxWidth: 14,
          barGap: "20%",
        },
        {
          name: "model (LightGBM)",
          type: "bar",
          data: champion.map((r) => pick(r)),
          itemStyle: { color: tokens["series-2"], borderRadius: [4, 4, 0, 0] },
          barMaxWidth: 14,
        },
      ],
    };
  }, [baseline, champion, deltas, metric, mini, tokens]);

  if (mini) {
    if (!baseline.length || !champion.length) return null;
    return (
      <Chart
        option={option}
        className="chart chart-mini"
        label="Grouped bar chart of MAPE per forecast horizon, model against seasonal-naive baseline. The model section below has the full version with a MAE toggle and a table view."
      />
    );
  }

  if (!baseline.length || !champion.length) {
    return (
      <EmptyPanel title="No per-horizon backtest in this artifact">
        <code>model.json</code> carries only overall metrics on this run; the by-horizon
        comparison appears once <code>models.train</code> publishes it.
      </EmptyPanel>
    );
  }

  return (
    <>
      <div className="chart-toolbar">
        <span className="mono-note">metric</span>
        <div className="seg" role="group" aria-label="Metric">
          {(["MAPE", "MAE"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={metric === m}
              onClick={() => setMetric(m)}
            >
              {m}
            </button>
          ))}
        </div>
      </div>
      <ChartWithTable
        caption="Backtest error per forecast horizon for the model and the seasonal-naive baseline, on identical folds."
        chart={
          <Chart
            option={option}
            label={`Grouped bar chart of ${metric} per forecast horizon, model against seasonal-naive baseline.`}
          />
        }
        rows={champion.map((r, i) => ({
          horizon: r.horizon_h,
          model: r,
          base: baseline[i],
          delta: deltas[i],
        }))}
        columns={[
          { key: "h", label: "Horizon (h)", render: (r) => r.horizon },
          {
            key: "bm",
            label: "Baseline MAE (MWh)",
            render: (r) => (r.base ? compact.format(r.base.mae) : "—"),
          },
          { key: "mm", label: "Model MAE (MWh)", render: (r) => compact.format(r.model.mae) },
          {
            key: "bp",
            label: "Baseline MAPE (%)",
            render: (r) => (r.base ? precise.format(r.base.mape_pct) : "—"),
          },
          { key: "mp", label: "Model MAPE (%)", render: (r) => precise.format(r.model.mape_pct) },
          {
            key: "d",
            label: "MAE delta (%)",
            render: (r) => (r.delta ? precise.format(r.delta.mae_delta_pct) : "—"),
          },
        ]}
      />
    </>
  );
}
