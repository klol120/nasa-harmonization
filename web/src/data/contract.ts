/**
 * Shapes the UI works with. Every data source (the burning-calendar API, or a file the user loads)
 * is normalised into these before the UI touches it.
 */

export type Sensor = "modis_raw" | "viirs_raw" | "harmonized";
export const SENSORS: Sensor[] = ["modis_raw", "viirs_raw", "harmonized"];

export const SENSOR_LABEL: Record<Sensor, string> = {
  modis_raw: "MODIS raw",
  viirs_raw: "VIIRS raw",
  harmonized: "Harmonized",
};

/** Value columns a source can chart. The API provides fire-days only. */
export type Metric = "cell_days" | "fire_count" | "sum_frp";
export const METRICS: Metric[] = ["cell_days", "fire_count", "sum_frp"];

export const METRIC_LABEL: Record<Metric, string> = {
  cell_days: "Fire-days",
  fire_count: "Hotspot detections",
  sum_frp: "Fire radiative power (MW)",
};

export const METRIC_SHORT: Record<Metric, string> = {
  cell_days: "fire-days",
  fire_count: "detections",
  sum_frp: "MW",
};

/**
 * Unit label for a sensor's values. MODIS fire-days are a different, much smaller unit than the
 * VIIRS-equivalent harmonized values (data contract), so they are always labelled as MODIS units.
 */
export const unitFor = (sensor: Sensor, metric: Metric) =>
  metric === "cell_days" && sensor === "modis_raw" ? "MODIS fire-days" : METRIC_SHORT[metric];

/** [west, south, east, north] in degrees. */
export type BBox = [number, number, number, number];

export interface CalibrationEntry {
  month: number; // 1-12
  /** Multiplicative factor: VIIRS-equivalent fire-days per MODIS fire-day. */
  k: number;
  k_low?: number;
  k_high?: number;
  /** Additive term (fire-days), when the calibration is affine. */
  b?: number;
}

export interface ValidationSummary {
  holdout_years: number[];
  /** Weighted absolute percentage error, %. */
  wape?: number;
  mape?: number; // %
  rmse?: number;
  bias?: number; // %
  strategy?: string;
  note?: string;
}

/** A documented fire event to annotate the record (from news, reports or the team). */
export interface FireEvent {
  label: string; // "Oct 2019 Chouf/Damour wildfires"
  short?: string; // chart label, e.g. "Chouf fires"
  from: string; // YYYY-MM
  to: string; // YYYY-MM inclusive
  lat?: number;
  lon?: number;
  radius?: number; // degrees, for zooming the map
  note?: string;
}

/** Everything the UI needs to describe and caveat a dataset. */
export interface DatasetMeta {
  id: string;
  name: string;
  bbox: BBox;
  grid_deg: number;
  first_year: number;
  last_year: number;
  /** Last month with data, "YYYY-MM" (may be part of a display-only partial year). */
  last_month: string;
  /** Last month that counts in medians and trends, "YYYY-MM". Later months are shown but flagged. */
  last_complete_month: string;
  /** First month with data, per sensor, "YYYY-MM". */
  sensor_start: Partial<Record<Sensor, string>>;
  /** Metrics this source provides. */
  metrics: Metric[];
  calibration: CalibrationEntry[];
  calibration_strategy?: string;
  validation?: ValidationSummary;
  harmonized_unit?: string;
  /** Harmonized values up to here are modelled from MODIS, not detections ("YYYY-MM"). */
  estimate_until?: string;
  /** VIIRS joins the record on this date (YYYY-MM-DD). */
  splice_date?: string;
  /** Contract v0.5: from this date (YYYY-MM-DD) VIIRS is NOAA-20 calibrated to S-NPP. */
  viirs_switch_date?: string;
  /** Contract v0.5: NOAA-20 -> S-NPP factors c per calendar month. */
  continuation?: { strategy?: string; overlap_years?: [number, number]; factors: { month: number; c: number; c_low?: number; c_high?: number }[] };
  /** Years the anomaly baseline is computed over. */
  baseline_years?: [number, number];
  n_cells?: number;
  n_persistent_cells?: number;
  /** Region outline (outer rings, [lon, lat]); drawn on the map. */
  outline?: [number, number][][];
  /** Region name in its local script, used decoratively. */
  local_name?: string;
  /** Documented events shown on the calendar, charts and map. */
  events?: FireEvent[];
  generated_at?: string;
  /** Producer caveats for the about box. */
  caveats?: string[];
  notes?: string[];
}

/** One month of an area's record, summed over its cells, with the flags that apply to it. */
export interface AreaMonth {
  i: number; // year*12 + month-1
  /** Value per sensor; null = no data for that sensor (never "zero fires"). */
  values: Record<Sensor, number | null>;
  /** 90% band of the harmonized value (equal to it for observed months). */
  low: number | null;
  high: number | null;
  /** Harmonized anomaly z against the region's baseline, from the source (null if none). */
  z: number | null;
  /** Harmonized value is modelled from MODIS, not detections. */
  estimate: boolean;
  lowConfidence: boolean;
  /** A satellite outage touched the month. */
  gap: boolean;
  /** Shown but left out of medians and trends (partial month or display-only year). */
  partial: boolean;
  /** The feeding sensor covers only part of this month (e.g. the month in progress). */
  partialMonth: boolean;
  /**
   * What feeds the harmonized value (contract v0.5 region_monthly.source): MODIS, SNPP, NOAA20, or two
   * joined by "+" for a month split at a switch date. Null when unknown or no data.
   */
  source: string | null;
  /** Uncalibrated NOAA-20 fire-days (contract v0.5), null when NOAA-20 has no data. */
  noaa20: number | null;
}

export interface AreaSeries {
  nCells: number;
  months: AreaMonth[];
}

/** Hotspot-level row (FIRMS-like columns). Not served by the API yet. */
export interface HotspotRow {
  latitude: number;
  longitude: number;
  acq_date: string; // YYYY-MM-DD
  acq_time: string; // HHMM
  satellite: string;
  instrument: "MODIS" | "VIIRS";
  confidence: string; // MODIS 0-100, VIIRS l/n/h
  frp: number;
  daynight: "D" | "N";
  type: number;
  /** Pixel size in km (FIRMS scan = across-track, track = along-track). MODIS ≈ 1 km, VIIRS ≈ 0.375 km at nadir. */
  scan?: number;
  track?: number;
}

/** Year-month helpers; months are indexed as year*12 + (month-1). */
export const ym = (year: number, month: number) => year * 12 + (month - 1);
export const ymYear = (i: number) => Math.floor(i / 12);
export const ymMonth = (i: number) => (i % 12) + 1;
export const ymKey = (i: number) => `${ymYear(i)}-${String(ymMonth(i)).padStart(2, "0")}`;
export const parseYm = (s: string) => {
  const [y, m] = s.split("-").map(Number);
  return ym(y, m);
};

export const MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
