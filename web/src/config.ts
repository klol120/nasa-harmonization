import type { BBox, FireEvent, Metric, Sensor } from "./data/contract";

/**
 * Everything deployment- or region-specific lives here.
 *
 * Data comes from the burning-calendar API (backend/, `python -m firecal_api.cli serve`).
 * Set VITE_API_URL to point the app at another server.
 */
export const API_URL = ((import.meta.env.VITE_API_URL as string | undefined) ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export const DEFAULT_SENSOR: Sensor = "harmonized";
export const DEFAULT_METRIC: Metric = "cell_days";

/** Default analysis window in years back from the latest data. 0 = everything. */
export const DEFAULT_YEARS_BACK = 0;

export const HOTSPOT_EXPORT_LIMIT = 50_000;

/**
 * Display details for the regions the API serves (keyed by the export's region id).
 * Regions not listed here still work, with their id as the name.
 */
export interface RegionInfo {
  name: string;
  blurb?: string;
  /** Name in the local script, used decoratively. */
  localName?: string;
  /** Where the world view puts the region's marker [lon, lat] (default: centre of its box). */
  marker?: [number, number];
  /** Named sub-areas offered as quick picks. */
  presets?: { name: string; bbox: BBox }[];
  /** Documented fires (from news and agency reports) annotated on the calendar, charts and map. */
  events?: FireEvent[];
}

const LEBANON_EVENTS: FireEvent[] = [
  { label: "Oct 2007 forest fires", short: "Forest fires", note: "Widespread autumn wildfires across Mount Lebanon and the North.", from: "2007-10", to: "2007-10" },
  {
    label: "Oct 2019 Chouf/Damour wildfires",
    short: "Chouf fires",
    note: "Wildfires that spread through the pine forests south of Beirut in mid-October.",
    from: "2019-10",
    to: "2019-10",
    lat: 33.68,
    lon: 35.55,
    radius: 0.25,
  },
  {
    label: "Jul 2021 Akkar (Qobayat) fire",
    short: "Akkar fire",
    note: "A large forest fire in the Qobayat area of Akkar.",
    from: "2021-07",
    to: "2021-08",
    lat: 34.52,
    lon: 36.18,
    radius: 0.2,
  },
  {
    label: "2023–24 southern border fires",
    short: "Border fires",
    note: "Months of repeated fires along the southern border area.",
    from: "2023-10",
    to: "2024-11",
    lat: 33.15,
    lon: 35.45,
    radius: 0.22,
  },
];

export const REGION_INFO: Record<string, RegionInfo> = {
  lebanon: {
    name: "Lebanon",
    blurb: "Mediterranean dry-season wildfires and post-harvest burning, peak Aug–Oct",
    localName: "لبنان",
    marker: [35.86, 33.87],
    presets: [
      { name: "Akkar", bbox: [35.95, 34.4, 36.45, 34.7] },
      { name: "North", bbox: [35.7, 34.15, 36.15, 34.5] },
      { name: "Baalbek-Hermel", bbox: [36.0, 33.85, 36.65, 34.55] },
      { name: "Bekaa", bbox: [35.65, 33.35, 36.1, 33.95] },
      { name: "Mount Lebanon", bbox: [35.45, 33.6, 35.95, 34.3] },
      { name: "Chouf & Damour", bbox: [35.4, 33.55, 35.75, 33.8] },
      { name: "South", bbox: [35.1, 33.05, 35.55, 33.6] },
      { name: "Nabatieh", bbox: [35.4, 33.1, 35.85, 33.5] },
    ],
    events: LEBANON_EVENTS,
  },
  greece: {
    name: "Greece",
    blurb: "Mediterranean summer wildfires",
    localName: "Ελλάδα",
    marker: [22.5, 39.2],
    presets: [
      { name: "Attica", bbox: [23.3, 37.6, 24.2, 38.4] },
      { name: "Peloponnese", bbox: [21.1, 36.4, 23.5, 38.4] },
      { name: "Evia", bbox: [22.8, 37.9, 24.6, 39.1] },
      { name: "Evros", bbox: [25.6, 40.6, 26.7, 41.8] },
      { name: "Crete", bbox: [23.4, 34.8, 26.4, 35.7] },
    ],
    events: [
      { label: "Aug 2007 Peloponnese fires", short: "Peloponnese", note: "Deadly late-summer wildfires across the western Peloponnese.", from: "2007-08", to: "2007-08", lat: 37.6, lon: 21.9, radius: 0.6 },
      { label: "Jul 2018 Mati (Attica) fire", short: "Mati", note: "Wind-driven fire in eastern Attica.", from: "2018-07", to: "2018-07", lat: 38.04, lon: 23.99, radius: 0.15 },
      { label: "Aug 2021 Evia fires", short: "Evia", note: "Large wildfires in northern Evia during a heatwave.", from: "2021-08", to: "2021-08", lat: 38.85, lon: 23.3, radius: 0.35 },
      { label: "Jul 2023 Rhodes fire", short: "Rhodes", note: "Wildfire that forced mass evacuations on Rhodes.", from: "2023-07", to: "2023-07", lat: 36.1, lon: 27.9, radius: 0.25 },
      { label: "Aug 2023 Evros (Dadia) fire", short: "Evros", note: "One of the largest wildfires recorded in the EU.", from: "2023-08", to: "2023-09", lat: 40.95, lon: 26.0, radius: 0.4 },
    ],
  },
  eastmed: {
    name: "Eastern Mediterranean",
    blurb: "Lebanon, Syria, Israel, Palestine, Cyprus and southern Turkey",
    marker: [38.6, 35.4],
    presets: [
      { name: "Lebanon", bbox: [35.1, 33.05, 36.65, 34.7] },
      { name: "Cyprus", bbox: [32.2, 34.5, 34.65, 35.75] },
      { name: "Southern Turkey coast", bbox: [30.0, 36.0, 36.5, 37.5] },
      { name: "Syrian Jazira", bbox: [38.0, 35.5, 42.4, 37.4] },
    ],
    events: [
      { label: "Dec 2010 Mount Carmel fire", short: "Carmel", note: "Forest fire on Mount Carmel near Haifa.", from: "2010-12", to: "2010-12", lat: 32.75, lon: 35.0, radius: 0.15 },
      ...LEBANON_EVENTS,
      { label: "Jul–Aug 2021 southern Turkey fires", short: "Manavgat", note: "Wildfires along the Mediterranean coast around Manavgat.", from: "2021-07", to: "2021-08", lat: 36.8, lon: 31.4, radius: 0.4 },
    ],
  },
};

export const regionInfo = (id: string): RegionInfo => REGION_INFO[id] ?? { name: id.charAt(0).toUpperCase() + id.slice(1) };

/**
 * Header aliases for imported CSVs. Keys are contract fields; values are
 * accepted header names (case-insensitive).
 */
export const COLUMN_ALIASES: Record<string, string[]> = {
  cell_id: ["cell_id", "cell", "id", "grid_id"],
  lat: ["lat", "latitude", "cell_lat", "y", "lat_center"],
  lon: ["lon", "lng", "longitude", "cell_lon", "x", "lon_center"],
  year: ["year", "yr"],
  month: ["month", "mon", "mm"],
  date: ["date", "ym", "year_month", "acq_month"],
  sensor: ["sensor", "source", "instrument", "product"],
  cell_days: ["cell_days", "fire_days", "active_cell_days", "celldays"],
  fire_count: ["fire_count", "count", "hotspots", "detections", "n"],
  sum_frp: ["sum_frp", "frp", "frp_sum", "total_frp"],
};

/** Accepted sensor values in imported data and the contract sensor they map to. */
export const SENSOR_ALIASES: Record<string, Sensor> = {
  modis_raw: "modis_raw",
  modis: "modis_raw",
  modis_sp: "modis_raw",
  modis_nrt: "modis_raw",
  viirs_raw: "viirs_raw",
  viirs: "viirs_raw",
  viirs_snpp_sp: "viirs_raw",
  viirs_noaa20_nrt: "viirs_raw",
  viirs_noaa21_nrt: "viirs_raw",
  harmonized: "harmonized",
  harmonised: "harmonized",
  harmonized_modis_eq: "harmonized",
};
