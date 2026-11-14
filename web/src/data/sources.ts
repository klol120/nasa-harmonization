import { COLUMN_ALIASES, SENSOR_ALIASES } from "../config";
import { type Area, pointInArea } from "../lib/geo";
import {
  type AreaMonth,
  type AreaSeries,
  type BBox,
  type CellMonthlyRow,
  type DatasetMeta,
  type HotspotRow,
  type Metric,
  METRICS,
  type Sensor,
  SENSORS,
  parseYm,
  ym,
  ymKey,
} from "./contract";
import { aggregateFirms, isFirmsHeader } from "./firms";

export interface AreaQuery {
  area: Area;
  /** The area is the whole region: use every cell. */
  whole: boolean;
  metric: Metric;
  /** Leave out cells with persistent industrial / waste-burning sources. */
  excludePersistent: boolean;
}

export interface CellQuery {
  sensor: Sensor;
  metric: Metric;
  from: number; // month index, inclusive
  to: number;
  excludePersistent: boolean;
}

export type CellValues = Map<string, { lat: number; lon: number; value: number }>;

/**
 * A data source: the region's description, an area's monthly record, and per-cell values for the
 * map. Sums, bands and anomalies for an area are computed by the source (server-side for the API).
 */
export interface DataSource {
  id: string;
  label: string;
  kind: "api" | "upload";
  description?: string;
  load(): Promise<DatasetMeta>;
  areaSeries(q: AreaQuery, signal?: AbortSignal): Promise<AreaSeries>;
  cellWindow(q: CellQuery, signal?: AbortSignal): Promise<CellValues>;
  /** Individual detections (only imported FIRMS files have them). */
  hotspots?(range: [number, number], bbox: BBox, limit: number): Promise<HotspotRow[]>;
}

// ---------------------------------------------------------------------------
// Files the user loads: cells_monthly rows or a raw FIRMS hotspot CSV, kept in the browser.

/** Wraps a user-supplied file as a data source. */
export function uploadSource(name: string, records: Record<string, unknown>[], partialMeta: Partial<DatasetMeta> = {}): DataSource {
  const firms = records.length > 0 && isFirmsHeader(Object.keys(records[0]));
  const result = firms ? aggregateFirms(records as Record<string, string>[], partialMeta.grid_deg ?? 0.1) : { ...normalizeRecords(records), hotspots: null };
  const { rows, warnings, hotspots } = result;
  if (!rows.length) throw new Error(warnings[0] ?? "No usable rows found in file.");
  const id = `upload:${name}`;
  const meta = completeMeta(id, name, rows, partialMeta);
  meta.notes = [...(meta.notes ?? []), ...warnings];
  return {
    id,
    label: name,
    kind: "upload",
    description: firms ? `${hotspots!.length.toLocaleString()} FIRMS hotspots → ${rows.length.toLocaleString()} cell-months` : `${rows.length.toLocaleString()} rows from file`,
    load: async () => meta,
    areaSeries: async (q) => rowsAreaSeries(meta, rows, q.area, q.metric),
    cellWindow: async (q) => cellTotals(rows, q.sensor, q.metric, q.from, q.to),
    hotspots: hotspots
      ? async (range, bbox, limit) =>
          hotspots
            .filter((h) => {
              const [y, m] = h.acq_date.split("-").map(Number);
              const i = ym(y, m);
              return h.longitude >= bbox[0] && h.longitude <= bbox[2] && h.latitude >= bbox[1] && h.latitude <= bbox[3] && i >= range[0] && i <= range[1];
            })
            .slice(0, limit)
      : undefined,
  };
}

/** Monthly sums per sensor over the rows whose cell centre is in the area. */
function rowsAreaSeries(meta: DatasetMeta, rows: CellMonthlyRow[], area: Area, metric: Metric): AreaSeries {
  const inside = new Map<string, boolean>();
  const sums = new Map<number, Record<Sensor, number>>();
  for (const r of rows) {
    let v = inside.get(r.cell_id);
    if (v === undefined) {
      v = pointInArea(r.lon, r.lat, area);
      inside.set(r.cell_id, v);
    }
    if (!v) continue;
    const i = ym(r.year, r.month);
    const s = sums.get(i) ?? { modis_raw: 0, viirs_raw: 0, harmonized: 0 };
    s[r.sensor] += r[metric];
    sums.set(i, s);
  }
  const starts = Object.fromEntries(SENSORS.map((s) => [s, meta.sensor_start[s] ? parseYm(meta.sensor_start[s]!) : Infinity])) as Record<Sensor, number>;
  const first = Math.min(...Object.values(starts));
  const last = parseYm(meta.last_month);
  const lastComplete = parseYm(meta.last_complete_month);
  const months: AreaMonth[] = [];
  for (let i = first; i <= last; i++) {
    const s = sums.get(i);
    const values = Object.fromEntries(SENSORS.map((k) => [k, i >= starts[k] ? +(s?.[k] ?? 0).toFixed(2) : null])) as Record<Sensor, number | null>;
    months.push({ i, values, low: values.harmonized, high: values.harmonized, z: null, estimate: false, lowConfidence: false, gap: false, partial: i > lastComplete, partialMonth: false, source: null, noaa20: null });
  }
  return { nCells: [...inside.values()].filter(Boolean).length, months };
}

function cellTotals(rows: CellMonthlyRow[], sensor: Sensor, metric: Metric, from: number, to: number): CellValues {
  const m: CellValues = new Map();
  for (const r of rows) {
    if (r.sensor !== sensor) continue;
    const i = r.year * 12 + r.month - 1;
    if (i < from || i > to) continue;
    const c = m.get(r.cell_id) ?? { lat: r.lat, lon: r.lon, value: 0 };
    c.value += r[metric];
    m.set(r.cell_id, c);
  }
  return m;
}

// ---------------------------------------------------------------------------
// Normalisation: any reasonable column naming → contract rows.

function findColumn(header: string[], field: string): string | undefined {
  const lower = header.map((h) => h.toLowerCase());
  for (const alias of COLUMN_ALIASES[field] ?? [field]) {
    const idx = lower.indexOf(alias.toLowerCase());
    if (idx >= 0) return header[idx];
  }
  return undefined;
}

export function describeColumnMapping(header: string[]) {
  return Object.keys(COLUMN_ALIASES).map((field) => ({ field, column: findColumn(header, field) }));
}

export function normalizeRecords(records: Record<string, unknown>[]): { rows: CellMonthlyRow[]; warnings: string[] } {
  const warnings: string[] = [];
  if (!records.length) return { rows: [], warnings: ["File has no rows."] };
  const header = Object.keys(records[0]);
  const col = Object.fromEntries(Object.keys(COLUMN_ALIASES).map((f) => [f, findColumn(header, f)]));

  const missing = ["lat", "lon"].filter((f) => !col[f]);
  if (!col.year && !col.date) missing.push("year/month or date");
  if (!col.cell_days && !col.fire_count && !col.sum_frp) missing.push("cell_days, fire_count or sum_frp");
  if (missing.length) return { rows: [], warnings: [`Missing required column(s): ${missing.join(", ")}.`] };
  if (!col.sensor) warnings.push("No sensor column: all rows treated as harmonized.");
  if (!col.cell_days) warnings.push("No cell_days column: fire-days approximated from fire_count.");

  const unknownSensors = new Set<string>();
  const rows: CellMonthlyRow[] = [];
  for (const r of records) {
    const num = (f: string) => (col[f] ? Number(r[col[f]!]) : NaN);
    const lat = num("lat");
    const lon = num("lon");
    let year = num("year");
    let month = num("month");
    if ((!Number.isFinite(year) || !Number.isFinite(month)) && col.date) {
      const [y, m] = String(r[col.date]).split(/[-/]/).map(Number);
      year = y;
      month = m;
    }
    if (![lat, lon, year, month].every(Number.isFinite) || month < 1 || month > 12) continue;
    const rawSensor = col.sensor ? String(r[col.sensor]).trim().toLowerCase() : "harmonized";
    const sensor = SENSOR_ALIASES[rawSensor];
    if (!sensor) {
      unknownSensors.add(rawSensor);
      continue;
    }
    const fc = num("fire_count");
    const cd = num("cell_days");
    rows.push({
      cell_id: col.cell_id ? String(r[col.cell_id]) : `${lat.toFixed(3)}_${lon.toFixed(3)}`,
      lat,
      lon,
      year,
      month,
      sensor,
      cell_days: Number.isFinite(cd) ? cd : Number.isFinite(fc) ? Math.min(fc, 1) : 0,
      fire_count: Number.isFinite(fc) ? fc : 0,
      sum_frp: Number.isFinite(num("sum_frp")) ? num("sum_frp") : 0,
    });
  }
  if (unknownSensors.size)
    warnings.push(`Skipped rows with unknown sensor value(s): ${[...unknownSensors].slice(0, 5).join(", ")}. Add them to SENSOR_ALIASES in config.ts.`);
  return { rows, warnings };
}

/** Fills any meta fields the file did not provide, inferring them from the rows. */
export function completeMeta(id: string, name: string, rows: CellMonthlyRow[], m: Partial<DatasetMeta>): DatasetMeta {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  let minI = Infinity, maxI = -Infinity;
  const starts: Record<string, number> = {};
  const lats = new Set<number>();
  const has = { cell_days: false, fire_count: false, sum_frp: false };
  for (const r of rows) {
    w = Math.min(w, r.lon); e = Math.max(e, r.lon);
    s = Math.min(s, r.lat); n = Math.max(n, r.lat);
    const i = ym(r.year, r.month);
    minI = Math.min(minI, i); maxI = Math.max(maxI, i);
    starts[r.sensor] = Math.min(starts[r.sensor] ?? Infinity, i);
    if (lats.size < 400) lats.add(r.lat);
    if (r.cell_days) has.cell_days = true;
    if (r.fire_count) has.fire_count = true;
    if (r.sum_frp) has.sum_frp = true;
  }
  // Grid size = smallest spacing between distinct cell latitudes.
  const sorted = [...lats].sort((a, b) => a - b);
  let grid = Infinity;
  for (let i = 1; i < sorted.length; i++) grid = Math.min(grid, sorted[i] - sorted[i - 1]);
  const grid_deg = m.grid_deg ?? (Number.isFinite(grid) && grid > 0 ? +grid.toFixed(4) : 0.1);
  const half = grid_deg / 2;
  const metrics = METRICS.filter((k) => has[k]);
  return {
    id,
    name: m.name ?? name,
    bbox: m.bbox ?? ([w - half, s - half, e + half, n + half].map((v) => +v.toFixed(4)) as BBox),
    grid_deg,
    first_year: m.first_year ?? Math.floor(minI / 12),
    last_year: m.last_year ?? Math.floor(maxI / 12),
    last_month: m.last_month ?? ymKey(maxI),
    last_complete_month: m.last_complete_month ?? ymKey(maxI),
    sensor_start: m.sensor_start ?? Object.fromEntries(Object.entries(starts).map(([k, v]) => [k, ymKey(v)])),
    metrics: metrics.length ? metrics : ["cell_days"],
    calibration: m.calibration ?? [],
    validation: m.validation,
    harmonized_unit: m.harmonized_unit,
    outline: m.outline,
    local_name: m.local_name,
    events: m.events,
    generated_at: m.generated_at,
    notes: m.notes ?? [],
  };
}
