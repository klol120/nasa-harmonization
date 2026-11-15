import { useMemo } from "react";
import { MONTH_ABBR, parseYm, ymKey, ymMonth, ymYear } from "../data/contract";
import type { ForecastMonth } from "../data/api";
import { fmt } from "../lib/analytics";
import { UI } from "../lib/colors";
import { EChart, tooltipStyle } from "./EChart";

interface Props {
  forecast: ForecastMonth[];
  /** Recent observed months (month index, value), oldest first; omitted when they would not match the forecast. */
  history?: { i: number; value: number | null }[];
  /** Typical-year median per calendar month (index 0 = January), for comparison. */
  typical?: (number | null)[];
  unit: string;
}

const label = (i: number) => `${MONTH_ABBR[ymMonth(i) - 1]} ${String(ymYear(i)).slice(2)}`;
const r2 = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? null : +v.toFixed(2));

/** Recent months, then the outlook: expected value, likely range, and the typical year as a dotted guide. */
export function ForecastChart({ forecast, history = [], typical, unit }: Props) {
  const option = useMemo(() => {
    const fIdx = forecast.map((f) => parseYm(f.ym));
    const hist = history.filter((h) => h.i < fIdx[0]);
    const xs = [...hist.map((h) => h.i), ...fIdx];
    const nH = hist.length;
    const lastObs = nH ? hist[nH - 1].value : null;

    const histData = [...hist.map((h) => r2(h.value)), ...fIdx.map(() => null)];
    // The forecast line starts from the last observed month so the two read as one story.
    const fcData = xs.map((_, k) => (k === nH - 1 ? r2(lastObs) : k >= nH ? r2(forecast[k - nH].value) : null));
    const low = xs.map((_, k) => (k >= nH ? r2(forecast[k - nH].value_low) : null));
    const band = xs.map((_, k) => {
      if (k < nH) return null;
      const f = forecast[k - nH];
      return f.value_low !== null && f.value_high !== null ? r2(f.value_high - f.value_low) : null;
    });
    const typ = typical ? xs.map((i) => r2(typical[ymMonth(i) - 1])) : null;

    return {
      tooltip: {
        ...tooltipStyle,
        trigger: "axis",
        formatter: (ps: { dataIndex: number }[]) => {
          const k = ps[0].dataIndex;
          const i = xs[k];
          const head = `<b>${MONTH_ABBR[ymMonth(i) - 1]} ${ymYear(i)}</b>`;
          const t = typ?.[k] !== null && typ?.[k] !== undefined ? `Typical year ${fmt(typ[k]!)} ${unit}` : null;
          if (k < nH) return [head, `Observed ${histData[k] === null ? "no data" : `${fmt(histData[k]!)} ${unit}`}`, t].filter(Boolean).join("<br/>");
          const f = forecast[k - nH];
          return [
            `${head} · forecast`,
            `<b>Expected ${fmt(f.value)} ${unit}</b>`,
            f.value_low !== null && f.value_high !== null ? `Likely ${fmt(f.value_low)} – ${fmt(f.value_high)} (8 in 10 months)` : null,
            t,
          ]
            .filter(Boolean)
            .join("<br/>");
        },
      },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: UI.muted, fontSize: 11 },
        data: [...(nH ? ["Observed"] : []), "Forecast", "Likely range", ...(typ ? ["Typical year"] : [])],
      },
      grid: { left: 44, right: 12, top: 30, bottom: 24 },
      xAxis: {
        type: "category",
        data: xs.map(label),
        boundaryGap: false,
        axisLine: { lineStyle: { color: UI.grid } },
        axisTick: { show: false },
        axisLabel: { color: UI.muted, interval: xs.length > 14 ? 2 : 0 },
      },
      yAxis: {
        type: "value",
        min: 0,
        splitLine: { lineStyle: { color: UI.grid } },
        axisLabel: { color: UI.muted, formatter: (v: number) => fmt(v) },
      },
      series: [
        { type: "line", data: low, stack: "band", lineStyle: { opacity: 0 }, symbol: "none", silent: true, tooltip: { show: false } },
        {
          name: "Likely range",
          type: "line",
          data: band,
          stack: "band",
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(252,165,10,0.18)" },
          itemStyle: { color: "rgba(252,165,10,0.4)" },
          symbol: "none",
          silent: true,
        },
        ...(typ
          ? [
              {
                name: "Typical year",
                type: "line",
                data: typ,
                lineStyle: { color: UI.muted, width: 1.5, type: "dotted" },
                itemStyle: { color: UI.muted },
                symbol: "none",
              },
            ]
          : []),
        ...(nH
          ? [
              {
                name: "Observed",
                type: "line",
                data: histData,
                lineStyle: { color: UI.text, width: 2 },
                itemStyle: { color: UI.text },
                symbol: "none",
                z: 4,
              },
            ]
          : []),
        {
          name: "Forecast",
          type: "line",
          data: fcData,
          lineStyle: { color: UI.accent, width: 2.5, type: "dashed" },
          itemStyle: { color: UI.accent, borderColor: UI.surface, borderWidth: 1.5 },
          symbol: (_: unknown, p: { dataIndex: number }) => (p.dataIndex >= nH ? "circle" : "none"),
          symbolSize: 7,
          z: 5,
          markLine: nH
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: UI.faint, type: "solid", width: 1 },
                label: { color: UI.faint, fontSize: 10, formatter: "forecast →", position: "insideEndTop" },
                data: [{ xAxis: label(xs[nH - 1]) }],
              }
            : undefined,
        },
      ],
    };
  }, [forecast, history, typical, unit]);

  return <EChart id="forecast" title={`Burning outlook from ${forecast[0] ? ymKey(parseYm(forecast[0].ym)) : ""}`} option={option} height={280} />;
}
