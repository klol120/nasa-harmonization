import { useMemo } from "react";
import { type Sensor, SENSOR_LABEL, SENSORS } from "../data/contract";
import { type YearTotal, fmt, linearTrend } from "../lib/analytics";
import { SENSOR_COLOR, UI } from "../lib/colors";
import { EChart, tooltipStyle } from "./EChart";

interface Props {
  totals: Record<Sensor, YearTotal[]>;
  sensor: Sensor;
  compare: boolean;
  unit: string;
  selectedYear: number;
  viirsStartYear?: number;
  /** Documented events by month index; their years get a labelled marker. */
  events?: Map<number, string>;
  onSelectYear: (y: number) => void;
}

/**
 * Annual totals with a trend line. In compare mode it overlays raw MODIS, raw VIIRS
 * and harmonized, which is where the 2012 sensor jump (and its removal) shows.
 */
export function AnnualChart({ totals, sensor, compare, unit, selectedYear, viirsStartYear, events, onSelectYear }: Props) {
  const option = useMemo(() => {
    const years = [...new Set(SENSORS.flatMap((s) => totals[s].map((t) => t.year)))].sort((a, b) => a - b);
    const main = totals[sensor];
    const byYear = (ts: YearTotal[]) => new Map(ts.map((t) => [t.year, t]));
    const trend = linearTrend(main);
    const eventYears = new Map<number, string>();
    events?.forEach((label, i) => {
      const y = Math.floor(i / 12);
      if (!eventYears.has(y)) eventYears.set(y, label);
    });
    const eventPoints = (ts: YearTotal[]) => ({
      symbol: "circle",
      symbolSize: 7,
      itemStyle: { color: "#fff", borderColor: "#f37819", borderWidth: 2 },
      label: { show: true, position: "top", distance: 6, color: "#fca50a", fontSize: 10, fontWeight: 600, formatter: (p: any) => p.name },
      data: ts
        .filter((t) => eventYears.has(t.year) && t.coveredMonths > 0)
        .map((t) => ({ name: eventYears.get(t.year), coord: [String(t.year), t.total] })),
    });

    const viirsLine =
      viirsStartYear && years.includes(viirsStartYear)
        ? {
            silent: true,
            symbol: "none",
            lineStyle: { color: SENSOR_COLOR.viirs_raw, type: "dashed", width: 1 },
            // Along the line near the axis, so it never collides with event labels on top of the bars.
            label: { color: SENSOR_COLOR.viirs_raw, fontSize: 10, formatter: "VIIRS starts", position: "insideStartTop" },
            data: [{ xAxis: String(viirsStartYear) }],
          }
        : undefined;

    const series: any[] = [];
    if (compare) {
      for (const s of SENSORS) {
        const m = byYear(totals[s]);
        series.push({
          name: SENSOR_LABEL[s],
          type: "line",
          data: years.map((y) => {
            const t = m.get(y);
            return t && t.coveredMonths > 0 ? t.total : null;
          }),
          lineStyle: { color: SENSOR_COLOR[s], width: s === "harmonized" ? 2.5 : 1.75 },
          itemStyle: { color: SENSOR_COLOR[s] },
          symbol: "circle",
          symbolSize: s === "harmonized" ? 6 : 4,
          connectNulls: false,
          z: s === "harmonized" ? 5 : 3,
          markLine: s === "viirs_raw" ? viirsLine : undefined,
          markPoint: s === "harmonized" ? eventPoints(totals[s]) : undefined,
        });
      }
    } else {
      const m = byYear(main);
      series.push({
        name: SENSOR_LABEL[sensor],
        type: "bar",
        barMaxWidth: 18,
        data: years.map((y) => {
          const t = m.get(y);
          if (!t) return null;
          return {
            value: t.total,
            itemStyle: {
              color: y === selectedYear ? "#fcffa4" : t.complete ? "#f37819" : "rgba(243,120,25,0.35)",
              borderRadius: [2, 2, 0, 0],
            },
          };
        }),
        markLine: viirsLine,
        markPoint: eventPoints(main),
      });
      if (trend) {
        series.push({
          name: "Trend",
          type: "line",
          data: years.map((y) => (y >= trend.from && y <= trend.to ? +(trend.intercept + trend.slope * y).toFixed(2) : null)),
          lineStyle: { color: UI.text, width: 1.5, type: "dashed" },
          itemStyle: { color: UI.text },
          symbol: "none",
          silent: true,
        });
      }
    }

    return {
      tooltip: {
        ...tooltipStyle,
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(255,255,255,0.04)" } },
        formatter: (ps: any[]) => {
          const y = Number(ps[0].axisValue);
          const lines = [`<b>${y}</b>`];
          for (const p of ps) {
            if (p.seriesName === "Trend") continue;
            const s = SENSORS.find((k) => SENSOR_LABEL[k] === p.seriesName)!;
            const t = totals[s]?.find((x) => x.year === y);
            if (!t) continue;
            lines.push(
              `${p.marker}${p.seriesName}: ${t.coveredMonths ? fmt(t.total) : "no data"} ${t.coveredMonths ? unit : ""}${
                t.coveredMonths && !t.complete ? ` <i>(${t.coveredMonths}/12 months)</i>` : ""
              }`,
            );
          }
          return lines.join("<br/>");
        },
      },
      legend: compare
        ? { top: 0, right: 0, itemWidth: 14, itemHeight: 8, textStyle: { color: UI.muted, fontSize: 11 } }
        : undefined,
      grid: { left: 48, right: 12, top: compare ? 44 : 30, bottom: 24 },
      xAxis: {
        type: "category",
        data: years.map(String),
        axisLine: { lineStyle: { color: UI.grid } },
        axisTick: { show: false },
        axisLabel: { color: UI.muted, interval: (k: number) => years.length <= 14 || years[k] % 4 === 0 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: UI.grid } },
        axisLabel: { color: UI.muted, formatter: (v: number) => fmt(v) },
      },
      series,
    };
  }, [totals, sensor, compare, unit, selectedYear, viirsStartYear, events]);

  return (
    <EChart
      id="annual"
      title="Annual totals"
      option={option}
      height={250}
      onClick={(p) => p.name && onSelectYear(Number(p.name))}
    />
  );
}
