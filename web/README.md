# Wel3a · Burning Calendar (frontend prototype)

NASA Space Apps 2026, challenge #09: harmonizing MODIS and VIIRS hotspots into one burning-activity calendar.

This is the **frontend only**. It runs on **synthetic mock data** shaped exactly like the agreed data contract, so it can be swapped for the harmonization engine's output without touching UI code.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # static site in dist/ (works on GitHub Pages / Vercel / opened locally)
```

## Desktop app (Electron)

```bash
npm run app         # build the site, then open it as a desktop window
npm run app:start   # open the window using the last build
```

`electron/main.cjs` serves `dist/` from a local server on 127.0.0.1 and shows it in an Electron window. Links to other sites open in the normal browser. The app still needs internet for map tiles, satellite imagery and terrain.

## What's on screen

| Area | What it does |
|---|---|
| Top bar | Dataset picker (+ "Load your own file…"), **MODIS raw / VIIRS raw / Harmonized** toggle, metric (cell-days, detections, FRP), Export, Methods |
| Sidebar | Area of interest (presets, draw box/polygon, bounds or point + radius), date range, map layers, key events |
| KPIs | Total, average per year, peak month, record year, trend per decade |
| Map | MapLibre, grid cells / heat surface / hotspot points, area mask, draw tools, timeline scrubber with play |
| This month vs normal | Selected month vs the same month in every other year: % and z-score, rank, year to date |
| Burning calendar | Month × year heatmap, values or anomaly (z) mode; hatched = no coverage (never shown as zero); dashed = month in progress |
| Typical year | Median, middle 50 % and 10th–90th percentile per month, selected year on top. Labelled *not a forecast* |
| Annual totals | Bars + trend line, or **Compare sensors**: raw MODIS vs raw VIIRS vs harmonized (the 2012 jump demo) |
| Fire season by year | Start (10 %), peak and end (90 %) per year vs the typical season |
| Methods drawer | Pipeline, calibration factor k per month, validation (MAPE, bias, RMSE), caveats, references |
| Exports | Hotspots CSV (FIRMS columns), calendar CSV, analytics CSV, chart PNGs, map PNG |

The view state (dataset, sensor, metric, area, range, month) lives in the URL hash, so a link reproduces the view.

## Plugging in real data

Everything data-specific is in `src/config.ts` and `src/data/`. The UI only ever sees `Dataset = { meta, rows }` from `src/data/contract.ts`.

### Option A: static files from the pipeline (recommended for the demo)

1. Put the engine output in `public/data/<id>/`:
   - `cells_monthly.csv` (or `.json`): one row per cell × month × sensor
   - `meta.json`: optional, but strongly recommended (calibration, validation, gaps)
2. Register it in `src/config.ts → STATIC_DATASETS`:
   ```ts
   { id: "lebanon-real", label: "Lebanon (harmonized v1)", baseUrl: "./data/lebanon-real" }
   ```
   or set `VITE_DATA_URL=./data/lebanon-real` (it then also becomes the default).
3. Optional: `hotspotsUrl` pointing at a FIRMS-style CSV enables the hotspot export and points layer.

### Option B: drop a file in the running app

"Load your own file…" in the dataset picker accepts:
- a `cells_monthly` CSV/JSON (column names matched loosely, see `COLUMN_ALIASES`), with optional `meta.json`
- a **raw NASA FIRMS CSV** (archive or API). It is cleaned (type 0, MODIS confidence ≥ 30, VIIRS nominal/high), snapped to 0.1° and counted as cell-days per sensor. It gives MODIS raw and VIIRS raw only, since harmonization is the engine's job.

### The contract

```
cell_id, lat, lon, year, month, sensor, cell_days, fire_count, sum_frp
sensor ∈ { modis_raw, viirs_raw, harmonized }
```

`lat`/`lon` are cell centres. A `date` column (`YYYY-MM`) can replace `year` + `month`. Sensor values like `MODIS_SP` or `VIIRS_SNPP_SP` are mapped via `SENSOR_ALIASES`.

`meta.json` (all fields optional; missing ones are inferred from the rows):

```json
{
  "name": "Lebanon",
  "bbox": [35.0, 32.9, 36.7, 34.75],
  "grid_deg": 0.1,
  "last_complete_month": "2026-10",
  "sensor_start": { "modis_raw": "2000-11", "viirs_raw": "2012-01", "harmonized": "2000-11" },
  "gap_months": { "modis_raw": ["2001-06"], "viirs_raw": [], "harmonized": [] },
  "calibration": [{ "month": 1, "k": 2.1, "r2": 0.84, "n": 70 }],
  "validation": { "holdout_years": [2019, 2020, 2021], "mape": 14.2, "bias": 2.1, "rmse": 9.8 },
  "harmonized_unit": "MODIS-equivalent cell-days",
  "notes": ["Anything the team wants shown in the Methods drawer"]
}
```

`gap_months` matters: those months render as "no coverage" instead of zero fires.

## Regions and the world view

The app opens on a **world map** (`components/WorldPicker.tsx`). Pick a featured region, search a country, or click any country, and the map flies in to that region's dashboard. A link with `#src=…` skips the world view.

- Country outlines come from Natural Earth 1:50m (`world-atlas`, loaded lazily). The outline is drawn with a glow, used as the default area ("All of Lebanon"), and clips the mock data to the border.
- Featured regions (cards and pulsing markers) are in `FEATURED` in `src/data/regions.ts`.
- **Lebanon** uses a hand-tuned mock profile (Akkar, Chouf, Bekaa stubble burning, Oct 2019 and Jul 2021 fires, 2023–24 southern border fires). Every other country gets a seeded generic profile whose season depends on latitude and whose grid scales with country size (0.1° to 2°). See `src/data/mockProfiles.ts`.
- Governorate quick-picks for Lebanon are in `AREA_PRESETS` in `src/config.ts`.
- A real dataset can carry its own region border in `meta.json → outline` (outer rings as `[lon, lat]` arrays).
- The map offers a dark basemap or Esri satellite imagery, plus fire glow, grid cells, heat surface and hotspot point layers.

## Signature views

- **Globe landing** (`components/WorldPicker.tsx`): MapLibre v5 globe projection with an atmosphere, a seeded starfield and a slow spin that stops as soon as the user touches it. Picking a place flies from orbit down to the region.
- **Fire rings** (`charts/FireRings.tsx`): the record drawn like a tree cross-section on a canvas. Each ring is a year (oldest at the core), ring thickness follows the year total, the 12 sectors are months coloured by activity. Values tween when the sensor or area changes, so the raw-VIIRS jump shows as the rings swelling after 2012. Hover, click and arrow keys work; documented fires show as embers.
- **3D fire columns** (the 3D button on the map): each grid cell is extruded by its activity (MapLibre fill-extrusion), at either the analysis grid or the 1 km grid. Right-drag or Ctrl+drag rotates.

## Map precision

- **Analysis grid (default):** the dataset's own cells (0.1° ≈ 11 km for Lebanon). All charts and statistics use this grid and the harmonized numbers.
- **1 km mode** (toggle on the map): individual detections in the map window are re-gridded at 0.01° (~1 km), using the same metrics (cell-days, detections, FRP). These are raw MODIS + VIIRS detections, not calibrated, and the map labels them that way.
- **True pixel footprints:** turn on "Hotspot points" and zoom past level 10 to see each detection as its real pixel, scan × track km from FIRMS: MODIS ≈ 1 km at nadir (up to ~4.8 × 2 km at the swath edge), VIIRS ≈ 375 m (up to ~0.8 × 0.75 km). Hovering a pixel shows instrument, satellite, time, FRP, confidence and pixel size. Pixels are drawn north-up; real ones are rotated slightly by the orbit.
- FIRMS coordinates are pixel centres: a fire is somewhere inside the pixel, never more precise than that.

## Layout of the code

```
src/
  config.ts               data sources, defaults, presets, column aliases
  data/contract.ts        shared types (the data contract)
  data/sources.ts         mock / static / upload adapters + normalisation
  data/firms.ts           raw FIRMS CSV → contract rows
  data/mockGenerator.ts   seeded synthetic data + calibration/validation numbers
  lib/analytics.ts        series, climatology, anomalies, trend, seasons, events
  components/, charts/    UI (MapLibre map, ECharts charts)
```

## Notes

- Mock data is deterministic (seeded) and clearly badged "Mock data" in the UI and in every export header.
- The basemap is CARTO Dark Matter (no token). If it can't load (offline demo), the app keeps working without a basemap.
- MapLibre's worker is loaded from its standalone file (`setWorkerUrl`) because Vite's dependency pre-bundling breaks the inlined worker.
