import { useMemo } from "react";
import { MONTH_ABBR, ym } from "../data/contract";
import { type AnomalyCell, fmt, fmtPct } from "../lib/analytics";
import { DIVERGING, INFERNO, UI } from "../lib/colors";
import { EChart, tooltipStyle } from "./EChart";

export type CalendarMode = "value" | "anomaly";

interface Props {
  cells: AnomalyCell[];
  mode: CalendarMode;
  unit: string;
  selected: number;
  onSelect: (i: number) => void;
  markers: { year: number; label: string }[];
  /** Documented events by month index, drawn as a small flame dot. */
  events?: Map<number, string>;
}

/** Month × year burning calendar. Rows are months (Jan on top), columns are years. */
export function CalendarHeatmap({ cells, mode, unit, selected, onSelect, markers, events }: Props) {
  const option = useMemo(() => {
    const years = [...new Set(cells.map((c) => c.year))].sort((a, b) => a - b);
    const yIndex = new Map(years.map((y, k) => [y, k]));
    const vals = cells.filter((c) => c.value !== null).map((c) => c.value!);
    const max = Math.max(1, ...vals);

    // [x, y, colourValue, cellIndex]; colour uses sqrt so a few extreme months don't flatten the rest.
    const data: (number | null)[][] = [];
    const nodata: number[][] = [];
    const partial: number[][] = [];
    const lowConf: number[][] = [];
    cells.forEach((c, k) => {
      if (c.lowConfidence && c.value !== null) lowConf.push([yIndex.get(c.year)!, c.month - 1, k]);
      const x = yIndex.get(c.year)!;
      const y = c.month - 1;
      if (c.value === null) {
        nodata.push([x, y, k]);
        return;
      }
      const colour = mode === "value" ? Math.sqrt(c.value) : c.z === null ? null : Math.max(-3, Math.min(3, c.z));
      if (colour === null) partial.push([x, y, k]);
      else data.push([x, y, colour, k]);
      if (c.partial) partial.push([x, y, k]);
    });

    const sel = cells.findIndex((c) => c.i === selected);
    const selCell = sel >= 0 ? [[yIndex.get(cells[sel].year)!, cells[sel].month - 1]] : [];

    const tooltip = {
      ...tooltipStyle,
      formatter: (p: any) => {
        const c = cells[p.data[p.data.length - 1]];
        if (!c) return "";
        const head = `<b>${MONTH_ABBR[c.month - 1]} ${c.year}</b>`;
        if (c.value === null) return `${head}<br/><span style="color:${UI.muted}">No data for this month. Not counted as zero.</span>`;
        const lines = [`${head}`, `${fmt(c.value)} ${unit}${c.partial ? " <i>(partial year, not in medians)</i>" : ""}`];
        if (c.pct !== null) lines.push(`${fmtPct(c.pct)} vs ${MONTH_ABBR[c.month - 1]} median · z ${c.z!.toFixed(1)}`);
        if (c.estimate) lines.push(`<span style="color:${UI.muted}">Modelled estimate from MODIS (not detections)${c.lowConfidence ? " · <b>low confidence</b>" : ""}</span>`);
        if (c.gap) lines.push(`<span style="color:${UI.muted}">A satellite outage touched this month</span>`);
        const ev = events?.get(c.i);
        if (ev) lines.push(`<span style="color:#fca50a">● ${ev}</span>`);
        return lines.join("<br/>");
      },
    };

    return {
      tooltip,
      grid: { left: 40, right: 16, top: 22, bottom: 58 },
      xAxis: {
        type: "category",
        data: years.map(String),
        splitArea: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: UI.muted, interval: (k: number) => years.length <= 16 || years[k] % 2 === 0, fontSize: 10 },
      },
      yAxis: {
        type: "category",
        data: MONTH_ABBR,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: UI.muted, fontSize: 10 },
      },
      visualMap:
        mode === "value"
          ? {
              type: "continuous",
              min: 0,
              max: Math.sqrt(max),
              dimension: 2,
              seriesIndex: 0,
              orient: "horizontal",
              left: "center",
              bottom: 4,
              itemWidth: 10,
              itemHeight: 220,
              calculable: false,
              text: [`${fmt(max)} ${unit}`, "0"],
              textStyle: { color: UI.muted, fontSize: 10 },
              inRange: { color: INFERNO },
              formatter: (v: number) => fmt(v * v),
            }
          : {
              type: "continuous",
              min: -3,
              max: 3,
              dimension: 2,
              seriesIndex: 0,
              orient: "horizontal",
              left: "center",
              bottom: 4,
              itemWidth: 10,
              itemHeight: 220,
              text: ["z +3 · far above normal", "far below · z −3"],
              textStyle: { color: UI.muted, fontSize: 10 },
              inRange: { color: DIVERGING },
            },
      series: [
        {
          type: "heatmap",
          data,
          itemStyle: { borderColor: UI.surface, borderWidth: 1.5, borderRadius: 2 },
          emphasis: { itemStyle: { borderColor: "#fff", borderWidth: 1.5 } },
          progressive: 0,
        },
        // Overlays are custom series: ECharts heatmaps must be bound to a visualMap.
        // Empty slots first, so months outside the selected range read as "not shown" rather than missing.
        overlay(
          years.flatMap((_, x) => MONTH_ABBR.map((__, y) => [x, y, -1])),
          (r) => ({ type: "rect", shape: { ...inset(r, 1.5), r: 2 }, style: { fill: "rgba(255,255,255,0.025)" } }),
          0,
        ),
        overlay(nodata, (r) => ({ type: "rect", shape: inset(r, 0.75), style: { fill: { image: hatch(), repeat: "repeat" } as any } }), 2, false),
        overlay(partial, (r) => ({ type: "rect", shape: inset(r, 1.5), style: { fill: "transparent", stroke: UI.text, lineWidth: 1, lineDash: [3, 2] } }), 3),
        // Low-confidence estimates: a muted dot screen over the colour, so they read as "less sure".
        overlay(lowConf, (r) => ({ type: "rect", shape: inset(r, 1.5), style: { fill: { image: dots(), repeat: "repeat" } as any } }), 2),
        overlay(
          cells.flatMap((c) => (events?.has(c.i) ? [[yIndex.get(c.year)!, c.month - 1, -1]] : [])),
          (r) => ({
            type: "circle",
            shape: { cx: r.x + r.width - 4, cy: r.y + 4, r: 2.6 },
            style: { fill: "#ffffff", stroke: "#f37819", lineWidth: 1.2 },
          }),
          5,
        ),
        overlay(selCell.map(([x, y]) => [x, y, sel]), (r) => ({ type: "rect", shape: { ...inset(r, 0.5), r: 2 }, style: { fill: "transparent", stroke: "#ffffff", lineWidth: 2 } }), 4),
        {
          // Sensor-change markers: a dashed rule on the left edge of the year's column.
          type: "custom",
          silent: true,
          z: 5,
          data: markers.filter((m) => yIndex.has(m.year)).map((m) => [yIndex.get(m.year)!, 0, m.label]),
          encode: { x: 0, y: 1 },
          renderItem: (_: unknown, api: any) => {
            const top = api.coord([api.value(0), 0]);
            const bottom = api.coord([api.value(0), 11]);
            const [w, h] = api.size([1, 1]);
            const x = top[0] - w / 2 - 0.75;
            return {
              type: "group",
              children: [
                { type: "line", shape: { x1: x, y1: top[1] - h / 2 - 8, x2: x, y2: bottom[1] + h / 2 }, style: { stroke: "#9aa4bb", lineWidth: 1, lineDash: [3, 3] } },
                { type: "text", x: x + 3, y: top[1] - h / 2 - 15, style: { text: String(api.value(2)), fill: UI.muted, fontSize: 10 } },
              ],
            };
          },
        },
      ],
    };
  }, [cells, mode, unit, selected, markers, events]);

  return (
    <EChart
      id="calendar"
      title="Burning calendar"
      option={option}
      height={360}
      ariaLabel="Month by year heatmap of fire activity"
      onClick={(p) => {
        const k = p.data?.[p.data.length - 1];
        const c = cells[k];
        if (c) onSelect(ym(c.year, c.month));
      }}
    />
  );
}

type Rect = { x: number; y: number; width: number; height: number };
const inset = (r: Rect, d: number): Rect => ({ x: r.x + d, y: r.y + d, width: r.width - 2 * d, height: r.height - 2 * d });

/** A custom series that draws one shape per [x, y, cellIndex] item, sized to the heatmap cell. */
function overlay(data: number[][], shape: (r: Rect) => object, z: number, silent = true) {
  return {
    type: "custom",
    data,
    z,
    silent,
    encode: { x: 0, y: 1 },
    renderItem: (_: unknown, api: any) => {
      const [cx, cy] = api.coord([api.value(0), api.value(1)]);
      const [w, h] = api.size([1, 1]);
      return shape({ x: cx - w / 2, y: cy - h / 2, width: w, height: h });
    },
  };
}

let dotsCanvas: HTMLCanvasElement | null = null;
function dots() {
  if (dotsCanvas) return dotsCanvas;
  const c = document.createElement("canvas");
  c.width = c.height = 4;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(10, 13, 20, 0.55)";
  g.fillRect(0, 0, 2, 2);
  g.fillRect(2, 2, 2, 2);
  dotsCanvas = c;
  return c;
}

let hatchCanvas: HTMLCanvasElement | null = null;
function hatch() {
  if (hatchCanvas) return hatchCanvas;
  const c = document.createElement("canvas");
  c.width = c.height = 6;
  const g = c.getContext("2d")!;
  g.fillStyle = UI.noData;
  g.fillRect(0, 0, 6, 6);
  g.strokeStyle = "#394157";
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(0, 6);
  g.lineTo(6, 0);
  g.stroke();
  hatchCanvas = c;
  return c;
}
