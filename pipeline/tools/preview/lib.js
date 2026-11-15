// Pure helpers for the export preview (no DOM). Also loaded by check.mjs under Node.

// `key` = field name in cells_series files. MODIS is in different (smaller) units: own colour scale.
export const VARIABLES = {
  harmonized: { label: "Harmonized (VIIRS-equivalent fire-days)", field: "harmonized", key: "h" },
  viirs_raw: { label: "VIIRS raw fire-days", field: "viirs_raw", key: "v" },
  modis_raw: { label: "MODIS raw fire-days (MODIS units, own scale)", field: "modis_raw", key: "m" },
};

export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Year x month matrix from region_monthly.json rows. Missing months are undefined (no row). */
export function heatmapGrid(rows, field) {
  const years = [...new Set(rows.map((r) => r.year))].sort((a, b) => a - b);
  const byKey = new Map(rows.map((r) => [r.ym, r]));
  const cells = [];
  let max = 0;
  for (const y of years) {
    for (let m = 1; m <= 12; m++) {
      const r = byKey.get(`${y}-${String(m).padStart(2, "0")}`);
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

/** Values of one month per cell from a cells_series/{year}.json document: Map(cell_id -> value).
 *  Cells absent from the file had no fire-days that year: 0 when the region has data, else null. */
export function seriesMonthValues(doc, ym, key, dataAvailable, allCellIds) {
  const i = doc.ym.indexOf(ym);
  const out = new Map();
  if (i < 0) return out;
  for (const id of allCellIds) out.set(id, dataAvailable ? 0 : null);
  for (const [id, c] of Object.entries(doc.cells)) out.set(id, c[key][i]);
  return out;
}

/** Map legend label for a month: estimates must be labelled as modelled (contract 0.4). */
export function monthLabel(row) {
  if (!row) return "";
  if (!row.data_available) return `${row.ym}: no data`;
  const parts = [row.ym];
  if (row.is_estimate) parts.push("MODELLED ESTIMATE (not detections)");
  if (row.low_confidence) parts.push("low confidence");
  if (row.partial_month) parts.push("partial month");
  if (row.display_only) parts.push("partial year, display only");
  return parts.join(" · ");
}

export function tooltip(row, field) {
  if (!row) return "no row";
  const f = (v) => (v === null || v === undefined ? "no data" : Number(v).toFixed(1));
  const flags = ["is_estimate", "low_confidence", "has_gap", "partial_month", "display_only"]
    .filter((k) => row[k]).join(", ");
  return `${row.ym}  ${field}: ${f(row[field])}` +
    `\nharmonized ${f(row.harmonized)} [${f(row.harmonized_low)}, ${f(row.harmonized_high)}]` +
    `\nMODIS ${f(row.modis_raw)}  VIIRS ${f(row.viirs_raw)}  z ${f(row.anomaly_z)}` +
    (row.data_available ? "" : "\nNO DATA") + (flags ? `\nflags: ${flags}` : "");
}
