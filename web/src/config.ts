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
  portugal: {
    name: "Portugal",
    blurb: "Atlantic-Mediterranean summer wildfires, peak Jul–Oct",
    marker: [-8.0, 39.6],
    presets: [
      { name: "North", bbox: [-8.9, 41.0, -6.2, 42.15] },
      { name: "Centre", bbox: [-8.95, 39.6, -6.9, 41.0] },
      { name: "Alentejo", bbox: [-8.9, 37.4, -7.0, 39.5] },
      { name: "Algarve", bbox: [-8.99, 36.95, -7.4, 37.55] },
    ],
    events: [
      { label: "Aug 2003 fire season", short: "2003 fires", note: "A heatwave summer with some of the largest burned areas on Portugal's record.", from: "2003-07", to: "2003-08" },
      { label: "Jun 2017 Pedrógão Grande fire", short: "Pedrógão", note: "Deadly June wildfire in the Leiria district of central Portugal.", from: "2017-06", to: "2017-06", lat: 39.92, lon: -8.15, radius: 0.25 },
      { label: "Oct 2017 central and northern fires", short: "Oct 2017", note: "Hundreds of fires driven by the winds of Storm Ophelia.", from: "2017-10", to: "2017-10", lat: 40.4, lon: -8.2, radius: 0.6 },
      { label: "Sep 2024 Aveiro and north fires", short: "Sep 2024", note: "Wildfires across the Aveiro and Viseu districts in mid-September.", from: "2024-09", to: "2024-09", lat: 40.7, lon: -8.3, radius: 0.35 },
    ],
  },
  cyprus: {
    name: "Cyprus",
    blurb: "Summer wildfires in the Troodos and Limassol hills",
    localName: "Κύπρος",
    marker: [33.1, 34.95],
    presets: [
      { name: "Troodos", bbox: [32.6, 34.8, 33.1, 35.1] },
      { name: "Paphos", bbox: [32.27, 34.65, 32.75, 35.15] },
      { name: "Limassol hills", bbox: [32.8, 34.65, 33.35, 34.95] },
    ],
    events: [
      { label: "Jun 2016 Solea (Troodos) fire", short: "Solea", note: "Forest fire on the northern slopes of the Troodos mountains.", from: "2016-06", to: "2016-06", lat: 35.0, lon: 32.95, radius: 0.12 },
      { label: "Jul 2021 Arakapas fire", short: "Arakapas", note: "The deadliest wildfire in Cyprus in decades, in the Limassol hills.", from: "2021-07", to: "2021-07", lat: 34.85, lon: 33.15, radius: 0.12 },
      { label: "Jul 2025 Limassol fire", short: "Limassol", note: "Large wildfire in the villages north-west of Limassol.", from: "2025-07", to: "2025-07", lat: 34.8, lon: 32.85, radius: 0.12 },
    ],
  },
  syria: {
    name: "Syria",
    blurb: "Wheat-belt burning in the north-east and coastal forest fires, peak May–Oct",
    localName: "سوريا",
    marker: [38.5, 35.0],
    presets: [
      { name: "Coast (Latakia & Tartus)", bbox: [35.7, 34.6, 36.4, 36.0] },
      { name: "Jazira (north-east)", bbox: [38.0, 35.5, 42.4, 37.4] },
      { name: "Homs & Hama", bbox: [36.3, 34.5, 37.6, 35.6] },
      { name: "Damascus & south", bbox: [35.9, 32.3, 37.0, 33.8] },
    ],
    events: [
      { label: "May–Jun 2019 north-east crop fires", short: "Crop fires", note: "Widespread fires in ripe wheat and barley fields around Hasakah.", from: "2019-05", to: "2019-06", lat: 36.6, lon: 41.0, radius: 0.6 },
      { label: "Oct 2020 Latakia and Tartus fires", short: "Coast fires", note: "Wildfires across the forested coastal mountains.", from: "2020-10", to: "2020-10", lat: 35.3, lon: 36.05, radius: 0.3 },
      { label: "Jul 2025 Latakia fires", short: "Latakia", note: "Large forest fires in the northern Latakia mountains.", from: "2025-07", to: "2025-07", lat: 35.8, lon: 35.95, radius: 0.2 },
    ],
  },
  jordan: {
    name: "Jordan",
    blurb: "Few, small fires, mostly crop and stubble burning in the farmed north",
    localName: "الأردن",
    marker: [36.2, 31.2],
    presets: [
      { name: "Irbid", bbox: [35.65, 32.4, 36.1, 32.75] },
      { name: "Ajloun & Jerash", bbox: [35.6, 32.2, 36.0, 32.5] },
      { name: "Jordan Valley", bbox: [35.5, 31.0, 35.65, 32.7] },
    ],
  },
  turkey: {
    name: "Turkey",
    blurb: "Mediterranean and Aegean coastal wildfires, crop burning in the south-east",
    localName: "Türkiye",
    marker: [35.0, 39.0],
    presets: [
      { name: "Mediterranean coast", bbox: [29.0, 36.0, 36.5, 37.5] },
      { name: "Aegean", bbox: [26.0, 37.0, 28.9, 39.6] },
      { name: "Marmara", bbox: [26.0, 39.6, 31.0, 41.6] },
      { name: "South-east", bbox: [37.0, 36.6, 44.8, 38.6] },
    ],
    events: [
      { label: "Jul–Aug 2021 Manavgat fires", short: "Manavgat", note: "Wildfires along the Mediterranean coast around Manavgat.", from: "2021-07", to: "2021-08", lat: 36.8, lon: 31.4, radius: 0.4 },
      { label: "Jul–Aug 2021 Marmaris fires", short: "Marmaris", note: "Fires on the Aegean coast in the same heatwave.", from: "2021-07", to: "2021-08", lat: 36.85, lon: 28.27, radius: 0.25 },
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
