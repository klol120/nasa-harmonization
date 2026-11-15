import { API_URL, regionInfo } from "../config";
import type { Area } from "../lib/geo";
import { type AreaMonth, type AreaSeries, type BBox, type DatasetMeta, type Sensor, parseYm } from "./contract";
import { countryOutline } from "./regions";
import type { AreaQuery, CellQuery, CellValues, DataSource } from "./sources";

/** Client for the burning-calendar API (backend/firecal_api). Responses follow data contract v0.4/v0.5. */

export class ApiError extends Error {}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(`Can't reach the data server at ${API_URL}. Start it with "uv run python -m firecal_api.cli serve" in backend/.`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // not JSON
    }
    throw new ApiError(`Data server error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export interface RegionSummary {
  region: string;
  release_id: number;
  contract_version: string;
  generated_at: string | null;
  bbox: BBox;
  countries: string[];
  first_month: string;
  last_month: string;
  n_cells: number;
  n_persistent_cells: number;
  baseline_years: [number, number];
}

export const listRegions = () => getJson<RegionSummary[]>("/regions");

/** Weather fields served by /regions/{r}/weather. */
export type WeatherField = "t_mean_c" | "t_max_c" | "precip_mm" | "wind_ms" | "rh_pct";

/** One month of past weather at the region's fire hotspots, with its baseline normal, difference and z. */
export type WeatherMonth = {
  ym: string;
  year: number;
  month: number;
  n_days: number;
  complete: boolean;
  precip_pct_of_normal: number | null;
} & { [F in WeatherField]: number | null } & { [F in WeatherField as `${F}_normal` | `${F}_anom` | `${F}_z`]: number | null };

export interface RegionWeather {
  region: string;
  provider: string;
  attribution: string;
  note: string;
  baseline_years: [number, number];
  fields: Record<WeatherField, { label: string; unit: string }>;
  available: boolean;
  points: { lat: number; lon: number; weight: number }[];
  fetched_at?: string;
  months: WeatherMonth[];
}

/** State of the live pipeline for a region (/regions/{r}/live). */
export interface LiveStatus {
  region: string;
  /** False until the pipeline has stored at least one month for the region. */
  enabled: boolean;
  demo: boolean;
  /** A simulated replay is loaded and can be switched on. */
  demo_available: boolean;
  /** Changes whenever the region's live months change. */
  version: string | null;
  /** Last UTC day covered, "YYYY-MM-DD". */
  through: string | null;
  polled_at: string | null;
  first_month: string | null;
  last_month: string | null;
  last_detection_at: string | null;
  detections_24h: number;
  harmonization: { version: string; placeholder: boolean };
  source: string;
  months: { ym: string; fire_days: number; harmonized: number; through: string; partial_month: boolean; sensors: Record<string, number>; detections: number }[];
}

export const getLive = (region: string, demo: boolean, signal?: AbortSignal) =>
  getJson<LiveStatus>(`/regions/${encodeURIComponent(region)}/live${demo ? "?demo=1" : ""}`, { signal });

export const getWeather = (region: string, signal?: AbortSignal) => getJson<RegionWeather>(`/regions/${encodeURIComponent(region)}/weather`, { signal });

/** Name of the burning-outlook model (backend/firecal_api/outlook.py). */
export const OUTLOOK_MODEL = "outlook-hgb";
export type OutlookBaseline = "seasonal_5y" | "typical_year" | "last_year";
export type OutlookMethod = OutlookBaseline | "outlook";
type OutlookError = { mae: number; wape: number | null };

/** Region-level errors of one evaluation (outlook.summarize). `wape` = summed |error| / summed actual. */
export interface OutlookScore {
  n: number;
  actual_mean: number;
  model: OutlookError;
  candidate?: OutlookError;
  seasonal_5y: OutlookError;
  typical_year: OutlookError;
  last_year: OutlookError;
  best_baseline: OutlookBaseline;
  skill_vs_best: number;
  beats_baselines: boolean;
  within_25pct: number;
  months?: string[];
  interval_coverage?: number | null;
  by_horizon?: Record<string, OutlookScore>;
}

export interface ModelRun {
  run_id: number;
  model_name: string;
  model_version: string;
  release_id: number;
  target: string;
  params: Record<string, unknown>;
  metrics: {
    test?: OutlookScore;
    confirmation?: OutlookScore;
    method_evaluation?: OutlookScore;
    test_years?: [number, number];
    method_years?: [number, number];
    issued_after?: string;
    /** How this region's outlook is made, e.g. "machine-learning model 50% + 5-year average 50%". */
    method?: string;
    method_kind?: OutlookMethod;
    monthly_comparison?: Record<string, { candidate: number; method: OutlookMethod }>;
    /** Weight of the 5-year average (1 = the average alone). */
    blend?: number;
  };
  notes: string | null;
  created_at: string;
  is_current: boolean;
}

export interface ForecastMonth {
  ym: string;
  value: number;
  value_low: number | null;
  value_high: number | null;
}

export interface RegionForecast {
  region: string;
  run: ModelRun;
  months: ForecastMonth[];
}

/**
 * The newest outlook for a region's current release, or null when none has been published
 * (the model has not been run against this release yet).
 */
export async function getForecast(region: string, signal?: AbortSignal): Promise<RegionForecast | null> {
  const r = encodeURIComponent(region);
  const runs = await getJson<ModelRun[]>(`/regions/${r}/model-runs`, { signal });
  // Newest first. Prefer a run on the current release; the pipeline loads a new release every day, so
  // until the model runs again the newest earlier outlook is still shown (the page says so).
  const outlooks = runs.filter((x) => x.model_name === OUTLOOK_MODEL);
  const run = outlooks.find((x) => x.is_current) ?? outlooks[0];
  if (!run) return null;
  const p = await getJson<{ months: ForecastMonth[] }>(`/regions/${r}/predictions?run_id=${run.run_id}&level=region`, { signal });
  return { region, run, months: p.months };
}

export async function getForecastCells(region: string, runId: number, month: string, gridDeg: number, signal?: AbortSignal): Promise<CellValues> {
  const query = new URLSearchParams({ run_id: String(runId), level: "cell", from: month, to: month });
  const { rows } = await getJson<{ rows: { cell_id: string; value: number }[] }>(
    `/regions/${encodeURIComponent(region)}/predictions?${query}`, { signal },
  );
  const cells: CellValues = new Map();
  for (const { cell_id, value } of rows) {
    // The export contract indexes the grid north and east from (-90°, -180°).
    const [row, col] = cell_id.split("_").map(Number);
    if (Number.isInteger(row) && Number.isInteger(col) && value > 0) {
      cells.set(cell_id, { lat: (row + 0.5) * gridDeg - 90, lon: (col + 0.5) * gridDeg - 180, value });
    }
  }
  return cells;
}

/** A region_monthly / aggregate row (contract field names). */
interface MonthRow {
  ym: string;
  modis_raw: number | null;
  viirs_raw: number | null;
  noaa20_raw?: number | null; // v0.5
  harmonized: number | null;
  harmonized_low: number | null;
  harmonized_high: number | null;
  anomaly_z: number | null;
  source?: string | null; // v0.5
  is_estimate: boolean;
  has_gap: boolean;
  data_available: boolean;
  partial_month: boolean;
  display_only: boolean;
  low_confidence: boolean;
}

interface CellFeature {
  properties: { cell_id: string; lat_center: number; lon_center: number; is_persistent: boolean };
}

interface SeriesFile {
  ym: string[];
  cells: Record<string, { h: (number | null)[]; m: (number | null)[]; v: (number | null)[] }>;
}

const SERIES_KEY: Record<Sensor, "h" | "m" | "v"> = { harmonized: "h", modis_raw: "m", viirs_raw: "v" };

function toAreaMonth(r: MonthRow): AreaMonth {
  return {
    i: parseYm(r.ym),
    values: { harmonized: r.data_available ? r.harmonized : null, modis_raw: r.modis_raw, viirs_raw: r.viirs_raw },
    low: r.data_available ? r.harmonized_low : null,
    high: r.data_available ? r.harmonized_high : null,
    z: r.anomaly_z,
    estimate: r.is_estimate,
    lowConfidence: r.low_confidence,
    gap: r.has_gap,
    // display_only (the partial 2026) is shown but excluded from baselines, like a month in progress.
    partial: r.partial_month || r.display_only,
    partialMonth: r.partial_month,
    source: r.source ?? null,
    noaa20: r.noaa20_raw ?? null,
  };
}

const ymOfDate = (d?: string) => (d ? d.slice(0, 7) : undefined);

function areaBody(area: Area) {
  if (area.kind === "polygon") {
    const ring = area.ring.map(([x, y]) => [x, y]);
    const [a, b] = [ring[0], ring[ring.length - 1]];
    if (a[0] !== b[0] || a[1] !== b[1]) ring.push([a[0], a[1]]);
    return { polygon: [ring] };
  }
  return { bbox: area.bbox };
}

export function apiSource(summary: RegionSummary): DataSource {
  const id = summary.region;
  const info = regionInfo(id);
  const q = `release=${summary.release_id}`;
  // Months after the release's last day of data come from the live pipeline (live=1); demo adds a simulated replay.
  let demo = false;
  const lq = () => `${q}&live=1${demo ? "&demo=1" : ""}`;
  const base = `/regions/${encodeURIComponent(id)}`;
  let monthly: Promise<MonthRow[]> | null = null;
  let cells: Promise<Map<string, { lat: number; lon: number; persistent: boolean }>> | null = null;
  const series = new Map<number, Promise<SeriesFile>>();

  const getMonthly = () => (monthly ??= getJson<MonthRow[]>(`${base}/monthly?${lq()}`));
  const getCells = () =>
    (cells ??= getJson<{ features: CellFeature[] }>(`${base}/cells?${q}`).then(
      (fc) => new Map(fc.features.map((f) => [f.properties.cell_id, { lat: f.properties.lat_center, lon: f.properties.lon_center, persistent: f.properties.is_persistent }])),
    ));
  const getSeries = (year: number) => {
    let p = series.get(year);
    if (!p) {
      p = getJson<SeriesFile>(`${base}/series/${year}?${lq()}`);
      p.catch(() => series.delete(year)); // let a failed year be retried
      series.set(year, p);
    }
    return p;
  };

  return {
    id: `api:${id}`,
    label: info.name,
    description: info.blurb,

    refresh(opts) {
      if (opts?.demo !== undefined) demo = opts.demo;
      monthly = null;
      for (const y of [...series.keys()]) if (opts?.fromYear === undefined || y >= opts.fromYear) series.delete(y);
    },

    async load(): Promise<DatasetMeta> {
      const [m, rows] = await Promise.all([getJson<any>(`${base}/meta?${q}`), getMonthly()]);
      const avail = rows.filter((r) => r.data_available);
      const complete = avail.filter((r) => !r.partial_month);
      const estimates = rows.filter((r) => r.is_estimate);
      const cal = m.calibration ?? {};
      const val = m.validation;
      const chosen = val?.strategies?.find((s: any) => s.strategy === cal.strategy) ?? val?.strategies?.[0];
      const test: number[] = val?.holdout?.test ?? [];
      const fit: number[] = val?.holdout?.fit ?? [];
      const years = (a?: number, b?: number) => (a && b ? Array.from({ length: b - a + 1 }, (_, k) => a + k) : []);
      const outline = summary.countries.length === 1 ? await countryOutline(summary.countries[0]) : undefined;
      return {
        id,
        name: info.name,
        bbox: m.bbox,
        grid_deg: 0.05,
        first_year: Number(m.time.first_month.slice(0, 4)),
        last_year: Number((avail.at(-1)?.ym ?? m.time.last_month).slice(0, 4)),
        last_month: avail.at(-1)?.ym ?? m.time.last_month,
        last_complete_month: complete.at(-1)?.ym ?? m.time.last_month,
        sensor_start: {
          harmonized: m.time.first_month,
          modis_raw: ymOfDate(m.sources?.MODIS_SP?.first_date) ?? m.time.first_month,
          viirs_raw: ymOfDate(m.sources?.VIIRS_SNPP_SP?.first_date ?? m.time.splice_date),
        },
        metrics: ["cell_days"],
        calibration: (cal.factors ?? []).map((f: any) => ({ month: f.month, k: f.a, k_low: f.a_low, k_high: f.a_high, b: f.b })),
        calibration_strategy: cal.strategy,
        validation: chosen
          ? {
              holdout_years: years(test[0], test[1]),
              wape: chosen.wape * 100,
              bias: chosen.bias * 100,
              strategy: chosen.strategy,
              note: fit.length ? `Calibration fitted on ${fit[0]}–${fit[1]} and tested on ${test[0]}–${test[1]}.` : undefined,
            }
          : undefined,
        harmonized_unit: m.units,
        estimate_until: estimates.at(-1)?.ym,
        splice_date: m.time.splice_date,
        viirs_switch_date: m.time.viirs_switch_date,
        continuation: cal.continuation
          ? { strategy: cal.continuation.strategy, overlap_years: cal.continuation.overlap_years, factors: cal.continuation.factors ?? [] }
          : undefined,
        baseline_years: m.anomalies?.baseline_years,
        n_cells: m.n_cells,
        n_persistent_cells: m.n_persistent_cells,
        outline,
        local_name: info.localName,
        events: info.events,
        generated_at: m.generated_at,
        caveats: m.caveats,
        notes: [],
      };
    },

    async areaSeries(aq: AreaQuery, signal?: AbortSignal): Promise<AreaSeries> {
      if (aq.whole && !aq.excludePersistent) {
        return { nCells: summary.n_cells, months: (await getMonthly()).map(toAreaMonth) };
      }
      const body = { ...(aq.whole ? {} : areaBody(aq.area)), exclude_persistent: aq.excludePersistent };
      try {
        const res = await getJson<{ n_cells: number; months: MonthRow[] }>(`${base}/aggregate?${lq()}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
          signal,
        });
        return { nCells: res.n_cells, months: res.months.map(toAreaMonth) };
      } catch (e) {
        // No cells in the area: an empty record (the UI explains why).
        if (e instanceof ApiError && e.message.includes("404")) {
          return {
            nCells: 0,
            months: (await getMonthly()).map((r) => ({ ...toAreaMonth(r), values: { harmonized: null, modis_raw: null, viirs_raw: null }, low: null, high: null, z: null })),
          };
        }
        throw e;
      }
    },

    async cellWindow(cq: CellQuery): Promise<CellValues> {
      const grid = await getCells();
      const key = SERIES_KEY[cq.sensor];
      const out: CellValues = new Map();
      const first = parseYm(summary.first_month);
      const last = parseYm((await getMonthly()).at(-1)?.ym ?? summary.last_month);
      const from = Math.max(cq.from, first);
      const to = Math.min(cq.to, last);
      for (let year = Math.floor(from / 12); year <= Math.floor(to / 12); year++) {
        const f = await getSeries(year);
        const idx = f.ym.map(parseYm);
        for (const [cid, s] of Object.entries(f.cells)) {
          const c = grid.get(cid);
          if (!c || (cq.excludePersistent && c.persistent)) continue;
          let sum = 0;
          s[key].forEach((v, k) => {
            if (v !== null && idx[k] >= from && idx[k] <= to) sum += v;
          });
          if (sum <= 0) continue;
          const cur = out.get(cid);
          if (cur) cur.value += sum;
          else out.set(cid, { lat: c.lat, lon: c.lon, value: sum });
        }
      }
      return out;
    },
  };
}
