/**
 * The chrome every chart shares: recessive hairline grid, muted axes, a
 * crosshair tooltip, thin marks.
 *
 * Written once so no chart accidentally ships a heavy grid or a dashed axis
 * rule (dashing reads as "threshold", and on a gridline it means nothing).
 * Threshold lines *are* dashed here — that is the one place the meaning is
 * intended.
 */

import type { EChartsOption } from "echarts";

import type { Tokens } from "./theme";

export const AXIS_FONT = 11;

/**
 * What an axis-trigger tooltip actually receives.
 *
 * ECharts types the callback argument as a broad union covering every series
 * type; every chart here uses `[time, value]` pairs, so the callbacks are
 * declared as taking `unknown` (which is assignable to the wider parameter type)
 * and narrowed to this once, in one place, rather than with a cast per chart.
 */
export interface TooltipRow {
  seriesName: string;
  value: [string, number | null];
}

export const asRows = (params: unknown): TooltipRow[] => params as TooltipRow[];

export function baseOption(tokens: Tokens): EChartsOption {
  return {
    backgroundColor: "transparent",
    animationDuration: 260,
    textStyle: {
      fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
      color: tokens["text-secondary"],
    },
    grid: { left: 62, right: 24, top: 46, bottom: 52, containLabel: false },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: tokens.axis, width: 1 } },
      backgroundColor: tokens["surface-1"],
      borderColor: tokens.axis,
      borderWidth: 1,
      textStyle: { color: tokens["text-primary"], fontSize: 12 },
      // Bigger than the mark: a 2px line should not need a pixel-perfect landing.
      extraCssText: "box-shadow: 0 4px 16px rgba(0,0,0,0.14); border-radius: 8px;",
    },
    legend: {
      top: 4,
      // Right-aligned so it never collides with the y-axis name, which sits at
      // the top-left of the plot.
      right: 0,
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 3,
      itemGap: 18,
      // Legend text wears text ink, never the series colour.
      textStyle: { color: tokens["text-secondary"], fontSize: 12 },
      inactiveColor: tokens["text-muted"],
    },
  };
}

export function timeAxis(tokens: Tokens) {
  return {
    type: "time" as const,
    axisLine: { lineStyle: { color: tokens.axis } },
    axisTick: { show: false },
    axisLabel: {
      color: tokens["text-muted"],
      fontSize: AXIS_FONT,
      hideOverlap: true,
      // ECharts' default drops the month once the range is short, leaving bare
      // day numbers that could be any month.
      formatter: {
        year: "{yyyy}",
        month: "{MMM}",
        day: "{MMM} {d}",
        hour: "{d} {HH}:{mm}",
        minute: "{HH}:{mm}",
        second: "{HH}:{mm}:{ss}",
        millisecond: "{HH}:{mm}:{ss}",
        none: "{MMM} {d}",
      },
    },
    splitLine: { show: false },
  };
}

export function valueAxis(tokens: Tokens, name: string, extra: Record<string, unknown> = {}) {
  return {
    type: "value" as const,
    name,
    nameLocation: "end" as const,
    nameGap: 14,
    nameTextStyle: { color: tokens["text-muted"], fontSize: AXIS_FONT, align: "left" as const },
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: tokens["text-muted"], fontSize: AXIS_FONT },
    // Hairline, solid, one shade off the surface.
    splitLine: { lineStyle: { color: tokens.grid, width: 1, type: "solid" as const } },
    ...extra,
  };
}

type MarkLineLabelPosition = "insideEndTop" | "insideEndBottom" | "insideStartTop";

function thresholdStyle(
  tokens: Tokens,
  label: string,
  color: string,
  position: MarkLineLabelPosition,
) {
  return {
    lineStyle: { color, type: "dashed" as const, width: 1.5 },
    label: {
      formatter: label,
      position,
      color: tokens["text-secondary"],
      fontSize: 11,
      // A chip on the surface, so the label never sits on top of a mark.
      backgroundColor: tokens["surface-1"],
      padding: [2, 5],
      borderRadius: 4,
    },
  };
}

/**
 * A dashed reference rule — the one legitimate use of dashing on a chart
 * (dashing a *gridline* would read as "threshold" when it means nothing).
 *
 * `above` staggers the label so two nearby thresholds do not overprint.
 */
export function thresholdLine(
  tokens: Tokens,
  value: number,
  label: string,
  color: string,
  above = true,
) {
  return {
    yAxis: value,
    ...thresholdStyle(tokens, label, color, above ? "insideEndTop" : "insideEndBottom"),
  };
}

/** The same rule where the value axis is x — the label has to sit upright. */
export function verticalThresholdLine(
  tokens: Tokens,
  value: number,
  label: string,
  color: string,
) {
  return {
    xAxis: value,
    ...thresholdStyle(tokens, label, color, "insideStartTop"),
    // Without this the label inherits the (vertical) line's rotation.
    label: {
      ...thresholdStyle(tokens, label, color, "insideStartTop").label,
      rotate: 0,
      distance: 4,
    },
  };
}

export const compact = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
export const precise = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
export const psiFormat = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

export function shortDay(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function shortDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "UTC",
  });
}
