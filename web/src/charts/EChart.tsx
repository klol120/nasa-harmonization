import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, CustomChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { UI } from "../lib/colors";

echarts.use([
  BarChart,
  CustomChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

/** Live chart instances by id, so the export menu can grab PNGs of every chart. */
export const chartRegistry = new Map<string, { chart: echarts.ECharts; title: string }>();

export const baseTextStyle = { color: UI.muted, fontFamily: "IBM Plex Sans, system-ui, sans-serif", fontSize: 11 };

export const tooltipStyle = {
  backgroundColor: "#0d111a",
  borderColor: "#2b3345",
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { color: UI.text, fontSize: 12, fontFamily: "IBM Plex Sans, system-ui, sans-serif" },
  extraCssText: "box-shadow: 0 8px 24px rgba(0,0,0,.45); border-radius: 6px;",
};

interface Props {
  id: string;
  title: string;
  option: echarts.EChartsCoreOption;
  height: number | string;
  onClick?: (params: any) => void;
  ariaLabel?: string;
}

export function EChart({ id, title, option, height, onClick, ariaLabel }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    const c = echarts.init(el.current!, undefined, { renderer: "canvas" });
    chart.current = c;
    chartRegistry.set(id, { chart: c, title });
    c.on("click", (p) => clickRef.current?.(p));
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current!);
    return () => {
      ro.disconnect();
      chartRegistry.delete(id);
      c.dispose();
    };
  }, [id, title]);

  useEffect(() => {
    chart.current?.setOption({ textStyle: baseTextStyle, animationDuration: 350, ...option }, { notMerge: true, lazyUpdate: true });
  }, [option]);

  return <div ref={el} style={{ height, width: "100%" }} role="img" aria-label={ariaLabel ?? title} />;
}
