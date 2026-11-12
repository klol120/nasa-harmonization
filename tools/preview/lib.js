// Pure helpers for the export preview (no DOM). Also loaded by check.mjs under Node.

export const VARIABLES = {
  harmonized: { label: "Harmonized (VIIRS-equivalent fire-days)", field: "harmonized" },
  viirs_raw: { label: "VIIRS raw fire-days", field: "viirs_raw" },
  modis_raw: { label: "MODIS raw fire-days", field: "modis_raw" },
};

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Year x month matrix from region_monthly.json rows. Missing months are undefined (no row). */
export function heatmapGrid(rows, field) {
  const years = [...new Set(rows.map((r) => r.year))].sort((a, b) => a - b);
  const byKey = new Map(rows.map((r) => [`${r.year}-${r.month}`, r]));
  const cells = [];
  let max = 0;
  for (const y of years) {
    for (let m = 1; m <= 12; m++) {
      const r = byKey.get(`${y}-${m}`);
      const v = r ? r[field] : undefined;
      if (typeof v === "number" && v > max) max = v;
      cells.push({ year: y, month: m, row: r, value: v ?? null, exists: !!r });
    }
  }
  return { years, cells, max };
}

/** Sequential colour (light yellow -> dark red) on a sqrt scale; null -> grey. */
export function colour(v, max) {
  if (v === null || v === undefined || Number.isNaN(v)) return "#d0d0d0";
  if (max <= 0) return "#fff7d6";
  const t = Math.sqrt(Math.max(0, v) / max);
  const stops = [[255, 247, 214], [254, 196, 79], [236, 112, 20], [153, 52, 4], [80, 20, 2]];
  const x = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const c = stops[i].map((s, k) => Math.round(s + f * (stops[i + 1][k] - s)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

/** Parse the calendar CSV (header row, empty field = null, booleans True/False). */
export function parseCalendarCSV(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.length);
  const header = lines[0].split(",");
  const num = new Set(["year", "month", "modis_raw", "viirs_raw", "harmonized", "harmonized_low",
    "harmonized_high", "anomaly_z"]);
  return lines.slice(1).map((line) => {
    const parts = line.split(",");
    const o = {};
    header.forEach((h, i) => {
      const s = parts[i];
      if (s === undefined || s === "") o[h] = null;
      else if (num.has(h)) o[h] = Number(s);
      else if (s === "True" || s === "False") o[h] = s === "True";
      else o[h] = s;
    });
    return o;
  });
}

/** Values of one month per cell: Map(cell_id -> value). */
export function monthValues(calendarRows, year, month, field) {
  const out = new Map();
  for (const r of calendarRows) if (r.year === year && r.month === month) out.set(r.cell_id, r[field]);
  return out;
}

export function tooltip(row, field) {
  if (!row) return "no row";
  const f = (v) => (v === null || v === undefined ? "no data" : Number(v).toFixed(1));
  const flags = ["is_estimate", "low_confidence", "has_gap", "partial_month", "display_only"]
    .filter((k) => row[k]).join(", ");
  return `${row.year}-${String(row.month).padStart(2, "0")}  ${field}: ${f(row[field])}` +
    `\nharmonized ${f(row.harmonized)} [${f(row.harmonized_low)}, ${f(row.harmonized_high)}]` +
    `\nMODIS ${f(row.modis_raw)}  VIIRS ${f(row.viirs_raw)}  z ${f(row.anomaly_z)}` +
    (row.data_available ? "" : "\nNO DATA") + (flags ? `\nflags: ${flags}` : "");
}
