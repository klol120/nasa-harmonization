import { useMemo } from "react";
import { MONTH_ABBR, MONTH_NAMES } from "../data/contract";
import { type MonthClimatology, type MonthPoint, fmt, fmtPct } from "../lib/analytics";
import { UI } from "../lib/colors";
import { EChart, tooltipStyle } from "./EChart";

interface Props {
  series: MonthPoint[];
  clim: MonthClimatology[];
  /** Years with any data, oldest first. */
  years: number[];
  a: number;
  b: number;
  onChange: (a: number, b: number) => void;
  unit: string;
  onSelectMonth: (year: number, month: number) => void;
}

const monthValues = (series: MonthPoint[], year: number) =>
  MONTH_ABBR.map((_, k) => series.find((p) => p.year === year && p.month === k + 1)?.value ?? null);

/** Two years side by side, month by month, against the typical year, with the difference in words. */
export function YearCompare({ series, clim, years, a, b, onChange, unit, onSelectMonth }: Props) {
  const va = useMemo(() => monthValues(series, a), [series, a]);
  const vb = useMemo(() => monthValues(series, b), [series, b]);

  // Totals over the months both years cover, so a partial year is compared fairly.
  const both = va.map((v, k) => (v !== null && vb[k] !== null ? k : -1)).filter((k) => k >= 0);
  const sum = (vals: (number | null)[]) => both.reduce((s, k) => s + (vals[k] ?? 0), 0);
  const ta = sum(va);
  const tb = sum(vb);
  const pct = tb > 0 ? ((ta - tb) / tb) * 100 : null;
  const biggest = both.length ? both.reduce((m, k) => (Math.abs((va[k] ?? 0) - (vb[k] ?? 0)) > Math.abs((va[m] ?? 0) - (vb[m] ?? 0)) ? k : m), both[0]) : -1;
  const gap = biggest >= 0 ? (va[biggest] ?? 0) - (vb[biggest] ?? 0) : 0;

  const option = useMemo(
    () => ({
      tooltip: {
        ...tooltipStyle,
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: UI.wash } },
        valueFormatter: (v: number | null) => (v === null || v === undefined ? "no data" : `${fmt(v)} ${unit}`),
      },
      legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: UI.muted, fontSize: 11 } },
      grid: { left: 44, right: 8, top: 30, bottom: 26 },
      xAxis: { type: "category", data: [...MONTH_ABBR], axisTick: { show: false }, axisLine: { lineStyle: { color: UI.grid } }, axisLabel: { color: UI.muted } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: UI.grid } }, axisLabel: { color: UI.muted, formatter: (v: number) => fmt(v) } },
      series: [
        { name: String(a), type: "bar", data: va, barGap: "12%", barWidth: "32%", itemStyle: { color: UI.accent, borderRadius: [4, 4, 0, 0] } },
        { name: String(b), type: "bar", data: vb, barWidth: "32%", itemStyle: { color: UI.markerText, borderRadius: [4, 4, 0, 0] } },
        {
          name: "Typical (median)",
          type: "line",
          data: clim.map((c) => (Number.isFinite(c.median) ? +c.median.toFixed(2) : null)),
          symbol: "none",
          lineStyle: { color: UI.faint, width: 1.5, type: "dashed" },
          itemStyle: { color: UI.faint },
          z: 3,
        },
      ],
    }),
    [va, vb, a, b, clim, unit],
  );

  const yearSelect = (value: number, label: string, set: (y: number) => void) => (
    <label className="select-wrap" title={label}>
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => set(Number(e.target.value))}>
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <section className="card compare-card">
      <header className="card-head">
        <div>
          <h3>Compare two years</h3>
          <p>Month by month, against the typical year · click a month to open it</p>
        </div>
        <div className="card-actions compare-pick">
          <i className="compare-dot" style={{ background: UI.accent }} aria-hidden />
          {yearSelect(a, "First year", (y) => onChange(y, b))}
          <button className="icon-btn" onClick={() => onChange(b, a)} aria-label="Swap the two years" title="Swap">
            <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden>
              <path d="M5 7h11m0 0-3-3m3 3-3 3M15 13H4m0 0 3-3m-3 3 3 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <i className="compare-dot" style={{ background: UI.markerText }} aria-hidden />
          {yearSelect(b, "Second year", (y) => onChange(a, y))}
        </div>
      </header>

      <EChart id="compare" title={`Fire activity ${a} vs ${b}`} option={option} height={260} onClick={(p) => typeof p.dataIndex === "number" && onSelectMonth(p.seriesIndex === 1 ? b : a, p.dataIndex + 1)} />

      {both.length ? (
        <div className="compare-stats">
          <div>
            <span>{a}</span>
            <b>{fmt(ta)}</b>
            <small>{unit}</small>
          </div>
          <div>
            <span>{b}</span>
            <b>{fmt(tb)}</b>
            <small>{unit}</small>
          </div>
          <div>
            <span>Difference</span>
            <b className={pct === null ? "" : pct > 10 ? "tone-warm" : pct < -10 ? "tone-cool" : ""}>{pct === null ? "–" : fmtPct(pct)}</b>
            <small>
              {a} vs {b}
              {both.length < 12 ? ` · ${both.length} shared months` : ""}
            </small>
          </div>
          <p className="compare-story">
            {a === b ? (
              "Pick two different years to compare them."
            ) : pct === null ? (
              `${b} had no fire activity in the months both years cover.`
            ) : (
              <>
                {a} had <b>{Math.abs(pct) < 5 ? "about the same" : `${Math.abs(Math.round(pct))}% ${pct > 0 ? "more" : "less"}`}</b> fire activity than {b}
                {biggest >= 0 && Math.abs(gap) > 0 ? (
                  <>
                    , and the biggest gap was in <b>{MONTH_NAMES[biggest]}</b> ({gap > 0 ? "+" : "−"}
                    {fmt(Math.abs(gap))} {unit})
                  </>
                ) : null}
                .
              </>
            )}
          </p>
        </div>
      ) : (
        <p className="muted small">These two years share no months with data.</p>
      )}
    </section>
  );
}
