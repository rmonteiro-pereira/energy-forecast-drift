/**
 * A thin ECharts wrapper: init once, `setOption` on change, dispose on unmount.
 *
 * Deliberately ~50 lines instead of a wrapper library. All this needs to do is
 * own an instance's lifecycle and resize it; a dependency for that would add a
 * React peer-version constraint to a project that has no other reason to care.
 *
 * `notMerge` is on: the option is rebuilt from scratch on every theme change,
 * and merging a light-mode option into a dark-mode one leaves stale colours on
 * whatever the new option happens not to mention.
 */

import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
// Type-only import from the barrel: types are erased at build time, so this
// costs nothing in the bundle while keeping one `EChartsOption` across the app.
import type { EChartsOption } from "echarts";
import { useEffect, useRef } from "react";

// Explicit registration rather than `import * as echarts from "echarts"`: the
// barrel import pulls in every chart type ECharts ships (map, tree, graph,
// gauge...), which is ~1.2 MB of JavaScript for a page that draws lines and
// bars. Registering the five pieces actually used cuts that by roughly two
// thirds and makes the dependency legible.
echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  CanvasRenderer,
]);

interface Props {
  option: EChartsOption;
  className?: string;
  /** Announced to screen readers in place of the canvas. */
  label: string;
}

export function Chart({ option, className = "chart", label }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const instance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!host.current) return;
    instance.current = echarts.init(host.current, undefined, { renderer: "canvas" });

    const observer = new ResizeObserver(() => instance.current?.resize());
    observer.observe(host.current);

    return () => {
      observer.disconnect();
      instance.current?.dispose();
      instance.current = null;
    };
  }, []);

  useEffect(() => {
    instance.current?.setOption(option, { notMerge: true });
  }, [option]);

  return <div ref={host} className={className} role="img" aria-label={label} />;
}
