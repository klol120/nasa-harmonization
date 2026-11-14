import { useMemo } from "react";
import { MONTH_ABBR } from "../data/contract";
import { type MonthClimatology, type MonthPoint, fmt } from "../lib/analytics";
import { UI } from "../lib/colors";
import { EChart, tooltipStyle } from "./EChart";

interface Props {
  clim: MonthClimatology[];
  year: number;
  yearSeries: MonthPoint[];
  unit: string;
  onSelectMonth: (month: number) => void;
}

/** Typical-year envelope (median, IQR, P10–P90) with the selected year on top. Not a forecast. */
export function ClimatologyChart({ clim, year, yearSeries, unit, onSelectMonth }: Props) {
  const option = useMemo(() => {
    const ok = (v: number) => (Number.isFinite(v) ? +v.toFixed(2) : null);
    const maxMedian = Math.max(...clim.map((c) => (Number.isFinite(c.median) ? c.median : 0)));
    // Peak months: median within 75% of the highest month.
    const peaks = clim.filter((c) => c.median >= maxMedian * 0.75 && maxMedian > 0).map((c) => c.month);
    const yearVals = MONTH_ABBR.map((_, k) => {
      const p = yearSeries.find((s) => s.month === k + 1);
      return p && p.value !== null ? p.value : null;
    });

    return {
      tooltip: {
        ...tooltipStyle,
        trigger: "axis",
        formatter: (ps: any[]) => {
          const k = ps[0].dataIndex;
          const c = clim[k];
          const yv = yearVals[k];
          return [
            `<b>${MONTH_ABBR[k]}</b> · ${c.n} years`,
            `Median ${fmt(c.median)} ${unit}`,
            `Middle 50%: ${fmt(c.q1)} – ${fmt(c.q3)}`,
            `10th–90th pct: ${fmt(c.p10)} – ${fmt(c.p90)}`,
            yv !== null ? `<b>${year}: ${fmt(yv)}</b>` : `${year}: no data`,
          ].join("<br/>");
        },
      },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: UI.muted, fontSize: 11 },
        data: ["Median", "Middle 50%", "10th–90th pct", String(year)],
      },
      grid: { left: 44, right: 12, top: 30, bottom: 24 },
      xAxis: {
        type: "category",
        data: MONTH_ABBR,
        boundaryGap: false,
        axisLine: { lineStyle: { color: UI.grid } },
        axisTick: { show: false },
        axisLabel: { color: UI.muted },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: UI.grid } },
        axisLabel: { color: UI.muted, formatter: (v: number) => fmt(v) },
      },
      series: [
        // Stacked-area trick: an invisible base plus the band height.
        { type: "line", data: clim.map((c) => ok(c.p10)), stack: "outer", lineStyle: { opacity: 0 }, symbol: "none", silent: true, tooltip: { show: false } },
        {
          name: "10th–90th pct",
          type: "line",
          data: clim.map((c) => ok(c.p90 - c.p10)),
          stack: "outer",
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(252,165,10,0.10)" },
          itemStyle: { color: "rgba(252,165,10,0.25)" },
          symbol: "none",
          silent: true,
        },
        { type: "line", data: clim.map((c) => ok(c.q1)), stack: "inner", lineStyle: { opacity: 0 }, symbol: "none", silent: true, tooltip: { show: false } },
        {
          name: "Middle 50%",
          type: "line",
          data: clim.map((c) => ok(c.q3 - c.q1)),
          stack: "inner",
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(252,165,10,0.24)" },
          itemStyle: { color: "rgba(252,165,10,0.5)" },
          symbol: "none",
          silent: true,
        },
        {
          name: "Median",
          type: "line",
          data: clim.map((c) => ok(c.median)),
          lineStyle: { color: "#fca50a", width: 2 },
          itemStyle: { color: "#fca50a" },
          symbol: "none",
          markArea: peaks.length
            ? {
                silent: true,
                itemStyle: { color: "rgba(255,255,255,0.035)" },
                label: { show: true, position: "insideTop", color: UI.faint, fontSize: 10, formatter: "peak" },
                data: contiguous(peaks).map(([a, b]) => [{ xAxis: MONTH_ABBR[a - 1] }, { xAxis: MONTH_ABBR[b - 1] }]),
              }
            : undefined,
        },
        {
          name: String(year),
          type: "line",
          data: yearVals,
          connectNulls: false,
          lineStyle: { color: UI.text, width: 2 },
          itemStyle: { color: UI.text, borderColor: UI.surface, borderWidth: 1.5 },
          symbol: "circle",
          symbolSize: 6,
          z: 5,
        },
      ],
    };
  }, [clim, year, yearSeries, unit]);

  return (
    <EChart
      id="climatology"
      title="Monthly climatology"
      option={option}
      height={250}
      onClick={(p) => typeof p.dataIndex === "number" && onSelectMonth(p.dataIndex + 1)}
    />
  );
}

function contiguous(months: number[]): [number, number][] {
  const out: [number, number][] = [];
  for (const m of months) {
    const last = out[out.length - 1];
    if (last && m === last[1] + 1) last[1] = m;
    else out.push([m, m]);
  }
  return out;
}
