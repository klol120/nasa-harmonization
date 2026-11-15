import { type AreaSeries, type Sensor, MONTH_ABBR, SENSOR_LABEL, parseYm, ym, ymMonth, ymYear } from "../data/contract";
import type { Area } from "./geo";
import type { FireEvent } from "../data/contract";

export interface MonthPoint {
  i: number; // year*12 + month-1
  year: number;
  month: number;
  value: number | null; // null = no coverage (never "zero fires")
  partial: boolean;
  /** Modelled from MODIS, not detections (harmonized, pre-VIIRS). */
  estimate?: boolean;
  lowConfidence?: boolean;
  /** A satellite outage touched the month. */
  gap?: boolean;
  /** Anomaly z from the source against its documented baseline; overrides the in-range z. */
  zRef?: number | null;
  /** The feeding sensor covers only part of the month. */
  partialMonth?: boolean;
  /** What feeds the harmonized value (contract v0.5), e.g. "SNPP" or "SNPP+NOAA20". */
  source?: string | null;
}

/** Month-by-month values of one sensor in the range, with missing months as null. */
export function toMonthPoints(series: AreaSeries, sensor: Sensor, range: [number, number]): MonthPoint[] {
  const byI = new Map(series.months.map((m) => [m.i, m]));
  const out: MonthPoint[] = [];
  for (let i = range[0]; i <= range[1]; i++) {
    const m = byI.get(i);
    const v = m?.values[sensor] ?? null;
    out.push({
      i,
      year: ymYear(i),
      month: ymMonth(i),
      // Exact values: rounding each month here made yearly sums drift from the exported totals.
      value: v,
      partial: m?.partial ?? false,
      estimate: sensor === "harmonized" && !!m?.estimate,
      lowConfidence: sensor === "harmonized" && !!m?.lowConfidence,
      gap: !!m?.gap,
      zRef: sensor === "harmonized" && m ? m.z : undefined,
      partialMonth: m?.partialMonth ?? false,
      source: sensor === "harmonized" ? (m?.source ?? null) : undefined,
    });
  }
  return out;
}

const quantile = (sorted: number[], q: number) => {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
};

export interface MonthClimatology {
  month: number;
  n: number;
  median: number;
  q1: number;
  q3: number;
  p10: number;
  p90: number;
  mean: number;
  sd: number;
  min: number;
  max: number;
}

/** Per-calendar-month statistics across years, from complete, covered months only. */
export function climatology(series: MonthPoint[], excludeYear?: number): MonthClimatology[] {
  return MONTH_ABBR.map((_, mi) => {
    const vals = series
      .filter((p) => p.month === mi + 1 && p.value !== null && !p.partial && p.year !== excludeYear)
      .map((p) => p.value!)
      .sort((a, b) => a - b);
    const mean = vals.reduce((a, b) => a + b, 0) / Math.max(1, vals.length);
    const sd = Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, vals.length - 1));
    return {
      month: mi + 1,
      n: vals.length,
      median: quantile(vals, 0.5),
      q1: quantile(vals, 0.25),
      q3: quantile(vals, 0.75),
      p10: quantile(vals, 0.1),
      p90: quantile(vals, 0.9),
      mean,
      sd,
      min: vals[0] ?? NaN,
      max: vals[vals.length - 1] ?? NaN,
    };
  });
}

export interface AnomalyCell extends MonthPoint {
  pct: number | null; // % vs median of that calendar month
  z: number | null;
}

/** Each month compared with its own calendar-month climatology. */
export function anomalies(series: MonthPoint[], clim: MonthClimatology[]): AnomalyCell[] {
  return series.map((p) => {
    const c = clim[p.month - 1];
    if (p.value === null || p.partial || !c.n) return { ...p, pct: null, z: null };
    const pct = c.median > 0 ? ((p.value - c.median) / c.median) * 100 : p.value > 0 ? 100 : 0;
    // The source's z (fixed baseline years, per the data contract) whenever the source provides z:
    // a null there means "sd = 0 or no data" and stays null rather than being replaced by a local z.
    const z = p.zRef !== undefined ? p.zRef : c.sd > 0 ? (p.value - c.mean) / c.sd : 0;
    return { ...p, pct: +pct.toFixed(1), z: z === null ? null : +z.toFixed(2) };
  });
}

export interface YearTotal {
  year: number;
  total: number;
  coveredMonths: number;
  complete: boolean;
}

export function annualTotals(series: MonthPoint[]): YearTotal[] {
  const byYear = new Map<number, YearTotal>();
  for (const p of series) {
    const t = byYear.get(p.year) ?? { year: p.year, total: 0, coveredMonths: 0, complete: false };
    if (p.value !== null && !p.partial) {
      t.total += p.value;
      t.coveredMonths++;
    }
    byYear.set(p.year, t);
  }
  return [...byYear.values()].map((t) => ({ ...t, total: +t.total.toFixed(2), complete: t.coveredMonths === 12 }));
}

/** Ordinary least squares on complete years. */
export function linearTrend(totals: YearTotal[]) {
  const pts = totals.filter((t) => t.complete);
  const n = pts.length;
  if (n < 3) return null;
  const mx = pts.reduce((a, t) => a + t.year, 0) / n;
  const my = pts.reduce((a, t) => a + t.total, 0) / n;
  let sxy = 0;
  let sxx = 0;
  for (const t of pts) {
    sxy += (t.year - mx) * (t.total - my);
    sxx += (t.year - mx) ** 2;
  }
  const slope = sxx ? sxy / sxx : 0;
  const intercept = my - slope * mx;
  return { slope, intercept, mean: my, pctPerDecade: my ? (slope * 10 * 100) / my : 0, from: pts[0].year, to: pts[n - 1].year };
}

export interface SeasonMetrics {
  year: number;
  total: number;
  start: number | null; // month 1-12 when 10% of the year's activity is reached
  peak: number | null;
  end: number | null; // month when 90% is reached
  length: number | null;
  complete: boolean;
}

export function seasonMetrics(series: MonthPoint[]): SeasonMetrics[] {
  const years = [...new Set(series.map((p) => p.year))];
  return years.map((year) => {
    const ms = series.filter((p) => p.year === year);
    const complete = ms.length === 12 && ms.every((p) => p.value !== null && !p.partial);
    const vals = ms.map((p) => (p.value !== null && !p.partial ? p.value : 0));
    const total = vals.reduce((a, b) => a + b, 0);
    if (total <= 0) return { year, total: 0, start: null, peak: null, end: null, length: null, complete };
    let cum = 0;
    let start: number | null = null;
    let end: number | null = null;
    let peak = 0;
    vals.forEach((v, k) => {
      cum += v;
      if (start === null && cum >= total * 0.1) start = ms[k].month;
      if (end === null && cum >= total * 0.9) end = ms[k].month;
      if (v > vals[peak]) peak = k;
    });
    return {
      year,
      total: +total.toFixed(2),
      start,
      peak: ms[peak].month,
      end,
      length: start !== null && end !== null ? end - start + 1 : null,
      complete,
    };
  });
}

export interface CurrentVsMedian {
  i: number;
  value: number;
  median: number;
  q1: number;
  q3: number;
  pct: number;
  z: number;
  n: number;
  rank: number; // 1 = highest on record for that calendar month
  ytd: { value: number; median: number; pct: number } | null;
  partial: boolean;
}

/** One month compared with the same calendar month in every other year in range. */
export function currentVsMedian(series: MonthPoint[], target: number): CurrentVsMedian | null {
  const p = series.find((s) => s.i === target);
  if (!p || p.value === null) return null;
  const others = series.filter((s) => s.month === p.month && s.year !== p.year && s.value !== null && !s.partial).map((s) => s.value!);
  if (!others.length) return null;
  const sorted = [...others].sort((a, b) => a - b);
  const median = quantile(sorted, 0.5);
  const mean = others.reduce((a, b) => a + b, 0) / others.length;
  const sd = Math.sqrt(others.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, others.length - 1));
  const rank = others.filter((v) => v > p.value!).length + 1;

  // Year-to-date through the target month vs the median YTD of other years.
  const ytdOf = (year: number) => {
    const ms = series.filter((s) => s.year === year && s.month <= p.month);
    if (ms.length < p.month || ms.some((s) => s.value === null)) return null;
    return ms.reduce((a, s) => a + s.value!, 0);
  };
  const cur = ytdOf(p.year);
  const otherYtd = [...new Set(series.map((s) => s.year))]
    .filter((y) => y !== p.year)
    .map(ytdOf)
    .filter((v): v is number => v !== null)
    .sort((a, b) => a - b);
  const ytdMedian = quantile(otherYtd, 0.5);

  return {
    i: target,
    value: p.value,
    median,
    q1: quantile(sorted, 0.25),
    q3: quantile(sorted, 0.75),
    pct: median > 0 ? ((p.value - median) / median) * 100 : 0,
    z: sd > 0 ? (p.value - mean) / sd : 0,
    n: others.length,
    rank,
    ytd: cur !== null && otherYtd.length ? { value: cur, median: ytdMedian, pct: ytdMedian > 0 ? ((cur - ytdMedian) / ytdMedian) * 100 : 0 } : null,
    partial: p.partial,
  };
}

export interface KeyEvent {
  id: string;
  label: string;
  detail: string;
  i?: number; // month to jump to
  year?: number;
  tone: "hot" | "cool" | "info" | "event";
  /** Where it happened, for documented events: the map zooms there. */
  loc?: { lat: number; lon: number; radius: number };
  note?: string;
}

export function keyEvents(series: MonthPoint[], anoms: AnomalyCell[], totals: YearTotal[], clim: MonthClimatology[], sensor: Sensor, unit: string): KeyEvent[] {
  const ev: KeyEvent[] = [];
  const complete = totals.filter((t) => t.complete);
  if (complete.length) {
    const rec = complete.reduce((a, b) => (b.total > a.total ? b : a));
    const low = complete.reduce((a, b) => (b.total < a.total ? b : a));
    ev.push({ id: "rec", label: `Record year ${rec.year}`, detail: `${fmt(rec.total)} ${unit}`, year: rec.year, i: ym(rec.year, 1), tone: "hot" });
    ev.push({ id: "low", label: `Quietest year ${low.year}`, detail: `${fmt(low.total)} ${unit}`, year: low.year, i: ym(low.year, 1), tone: "cool" });
  }
  const withData = clim.filter((c) => c.n > 0 && Number.isFinite(c.median));
  if (withData.length) {
    const peak = withData.reduce((a, b) => (b.median > a.median ? b : a));
    ev.push({ id: "peak", label: `Peak month: ${MONTH_ABBR[peak.month - 1]}`, detail: `median ${fmt(peak.median)} ${unit}`, tone: "info" });
  }
  [...anoms]
    .filter((a) => a.z !== null && a.z > 2 && (a.value ?? 0) > 0)
    .sort((a, b) => b.z! - a.z!)
    .slice(0, 4)
    .forEach((a) =>
      ev.push({
        id: `anom-${a.i}`,
        label: `${MONTH_ABBR[a.month - 1]} ${a.year} spike`,
        detail: `z = ${a.z!.toFixed(1)}, ${a.pct! > 0 ? "+" : ""}${Math.round(a.pct!)}% vs median`,
        i: a.i,
        tone: "hot",
      }),
    );
  if (sensor !== "harmonized") {
    const first = series.find((p) => p.value !== null);
    if (first) ev.push({ id: "start", label: `${SENSOR_LABEL[sensor]} record starts`, detail: `${MONTH_ABBR[first.month - 1]} ${first.year}`, i: first.i, tone: "info" });
  }
  return ev;
}

export function fmt(v: number | null | undefined, digits?: number) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  if (digits !== undefined) return v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  if (a >= 100_000) return `${(v / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })}k`;
  if (a >= 100) return Math.round(v).toLocaleString();
  if (a >= 10) return v.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/**
 * Upper quantile of the positive values (default 98th percentile): a "max" that one outlier
 * cell cannot set. Falls back to the true max when there are too few values for a quantile.
 */
export function robustMax(values: Iterable<number>, q = 0.98) {
  const v = [...values].filter((x) => x > 0).sort((a, b) => a - b);
  if (!v.length) return 0;
  if (v.length < 20) return v[v.length - 1];
  return v[Math.min(v.length - 1, Math.floor(q * (v.length - 1)))];
}

export const fmtPct = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v))}%`;

/** Median start / peak / end month across complete years: "the typical fire season". */
export function typicalSeason(seasons: SeasonMetrics[]) {
  const done = seasons.filter((s) => s.complete && s.start !== null);
  if (!done.length) return null;
  const med = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.floor((xs.length - 1) / 2)];
  return { start: med(done.map((s) => s.start!)), peak: med(done.map((s) => s.peak!)), end: med(done.map((s) => s.end!)), years: done.length };
}

/**
 * Documented events that fall in the date range and (when located) near the area,
 * each with how unusual its first month was in the current series.
 */
export function documentedEvents(events: FireEvent[] | undefined, area: Area, range: [number, number], anoms: AnomalyCell[]): KeyEvent[] {
  if (!events?.length) return [];
  const [w, s, e, n] = area.bbox;
  return events
    .filter((ev) => {
      const i = parseYm(ev.from);
      if (i < range[0] || i > range[1]) return false;
      if (ev.lat === undefined || ev.lon === undefined) return true;
      const pad = ev.radius ?? 0;
      return ev.lon >= w - pad && ev.lon <= e + pad && ev.lat >= s - pad && ev.lat <= n + pad;
    })
    .map((ev) => {
      const i = parseYm(ev.from);
      const c = anoms.find((x) => x.i === i);
      const detail =
        c && c.pct !== null ? `${fmtPct(c.pct)} vs a normal ${MONTH_ABBR[c.month - 1]}${c.z !== null ? ` · z ${c.z.toFixed(1)}` : ""}` : `${MONTH_ABBR[ymMonth(i) - 1]} ${ymYear(i)}`;
      return {
        id: `doc-${ev.from}-${ev.label}`,
        label: ev.label,
        detail,
        i,
        tone: "event" as const,
        note: ev.note,
        loc: ev.lat !== undefined && ev.lon !== undefined ? { lat: ev.lat, lon: ev.lon, radius: ev.radius ?? 0.2 } : undefined,
      };
    })
    .sort((a, b) => b.i - a.i);
}
