import { chartRegistry } from "../charts/EChart";
import { UI } from "./colors";
import { MONTH_ABBR } from "../data/contract";
import type { AnomalyCell, MonthClimatology, SeasonMetrics, YearTotal } from "./analytics";
import { toCsv } from "./csv";

export function downloadBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const downloadText = (name: string, text: string, type = "text/csv") => downloadBlob(name, new Blob([text], { type: `${type};charset=utf-8` }));

export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/** Month-level calendar with anomaly columns. */
export function calendarCsv(cells: AnomalyCell[], header: Record<string, string>) {
  const rows = cells.map((c) => ({
    year: c.year,
    month: c.month,
    month_name: MONTH_ABBR[c.month - 1],
    value: c.value ?? "",
    coverage: c.value === null ? "no_coverage" : c.partial ? "partial" : "complete",
    pct_vs_median: c.pct ?? "",
    z_score: c.z ?? "",
  }));
  return withHeader(toCsv(rows), header);
}

export function analyticsCsv(clim: MonthClimatology[], totals: YearTotal[], seasons: SeasonMetrics[], header: Record<string, string>) {
  const a = toCsv(
    clim.map((c) => ({
      month: c.month,
      month_name: MONTH_ABBR[c.month - 1],
      years: c.n,
      median: r(c.median),
      q1: r(c.q1),
      q3: r(c.q3),
      p10: r(c.p10),
      p90: r(c.p90),
      mean: r(c.mean),
      sd: r(c.sd),
    })),
  );
  const b = toCsv(
    totals.map((t) => {
      const s = seasons.find((x) => x.year === t.year);
      return {
        year: t.year,
        total: t.total,
        covered_months: t.coveredMonths,
        complete: t.complete,
        season_start: s?.start ? MONTH_ABBR[s.start - 1] : "",
        season_peak: s?.peak ? MONTH_ABBR[s.peak - 1] : "",
        season_end: s?.end ? MONTH_ABBR[s.end - 1] : "",
      };
    }),
  );
  return withHeader(`# Monthly climatology\n${a}\n\n# Annual totals and season metrics\n${b}`, header);
}

const r = (v: number) => (Number.isFinite(v) ? +v.toFixed(3) : "");

function withHeader(csv: string, header: Record<string, string>) {
  const lines = Object.entries(header).map(([k, v]) => `# ${k}: ${v}`);
  return `${lines.join("\n")}\n${csv}`;
}

/** PNG of one chart, or every registered chart stacked into one image. */
export function chartPng(id?: string) {
  const entries = [...chartRegistry.entries()].filter(([k]) => !id || k === id);
  if (!entries.length) return;
  if (id) {
    const [, { chart, title }] = entries[0];
    downloadDataUrl(`${slug(title)}.png`, chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: UI.surface }));
    return;
  }
  for (const [, { chart, title }] of entries) {
    downloadDataUrl(`${slug(title)}.png`, chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: UI.surface }));
  }
}

export function downloadDataUrl(name: string, url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
