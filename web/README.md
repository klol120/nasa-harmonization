# Phoenical · Burning Calendar (website)

The browser app (and Electron desktop app) for the harmonized MODIS + VIIRS burning calendar. It reads
everything from the API in [`../backend`](../backend/README.md), which serves the data contract
([`../data_contract.md`](../data_contract.md)).

```sh
npm ci
npm run dev          # http://localhost:5173, talks to the API at http://127.0.0.1:8000
npm run build        # type check + static site in dist/
npm run app          # build, then open it as a desktop window (Electron)
```

`VITE_API_URL` points the app at another API (it is baked in at build time, e.g. the Docker image is built
with the Azure API URL). The API must list the site's origin in `CORS_ORIGINS`.

## What's on screen

| Area | What it does |
|---|---|
| World view | Globe landing page: featured regions, country search, email-list sign-up |
| Top bar | Region picker, **MODIS raw / VIIRS raw / Harmonized**, Export, Methods, account |
| Sidebar | My areas (signed in), area of interest (presets, box, polygon, bounds, point + radius), date range, key events, map layers, digest sign-up |
| Map | MapLibre: grid cells, heat surface, 3D columns, satellite or dark basemap, timeline with play |
| Charts | This month vs normal, burning calendar (values or z), typical year (not a forecast), annual totals and the 2012 sensor comparison, fire season by year, fire rings |
| Methods | Calibration per month, validation, caveats |
| Exports | Calendar and analytics CSV, chart PNGs, map PNG |

Units are **fire-days** (0.05° cells with at least one detection per day). Months before 2012-01 are modelled
from MODIS and labelled as estimates; months without data show as "no data", never as zero. The address bar
shows only the page and region (`#/calendar/lebanon`); the rest of the view is kept with the browser history, and
the Share button copies a full link (`#/calendar/lebanon?s=harmonized&…`) that reproduces the view.

## Accounts (optional)

Nothing is gated. `src/account/` adds sign-in with Google, the email list, the "My areas" panel with fire
alerts, and the account menu. The API decides what is offered (`GET /auth/config`): the Google button appears
when the backend has `GOOGLE_CLIENT_ID`, and a local test sign-in when it has `AUTH_DEV_LOGIN=1`.

## Data source

The pipeline is the single source of truth: every region and month comes from the API, which serves the
pipeline's exports. There is no way to load your own files in the browser.

## Code layout

```
src/
  config.ts          API URL, region names, presets, documented fire events
  data/api.ts        API client and data source (contract v0.4)
  data/sources.ts    the DataSource interface the API client implements
  lib/analytics.ts   series, climatology, anomalies, trend, seasons, events
  components/, charts/   UI (MapLibre map, ECharts charts, world picker)
  account/           optional accounts (sign-in, email list, My areas)
electron/main.cjs    serves dist/ on 127.0.0.1:47615 inside a desktop window
```
