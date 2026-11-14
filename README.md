# Wel3a · Burning Calendar (NASA Space Apps 2026)

One repository for the whole project: a harmonized MODIS/VIIRS burning-activity calendar, and the app that
serves and shows it.

| folder | what | read first |
|---|---|---|
| [`pipeline/`](pipeline/) | **firecal**, the harmonization pipeline. FIRMS download → cleaning → 0.05° fire-days → MODIS→VIIRS calibration (monthly ratios, Terra-only correction, NOAA-20 continuation) → splice → anomalies → export. Also `python -m firecal add-country <Country>`. | `pipeline/CLAUDE.md`, `pipeline/docs/FINAL_RATIOS.md` |
| [`backend/`](backend/) | FastAPI + PostgreSQL. Loads the pipeline's exports as releases, checks every contract invariant, and serves regions, calendars and area aggregation. | `backend/README.md` |
| [`web/`](web/) | Vite/React/MapLibre frontend (with an Electron wrapper). Reads only the backend API. | `web/README.md` |

## Data flow

```
pipeline/  python -m firecal all --region R      ->  pipeline/data/export/{region}/  (contract 0.5)
backend/   python -m firecal_api.cli ingest       <-  pipeline/data/export (default EXPORT_DIR)
web/       VITE_API_URL=http://127.0.0.1:8000     <-  backend API
```

- **Shared exports.** The exports in git are `pipeline/data/export/*`: `meta.json`, `region_monthly.json`,
  `cells.geojson`, `calendar.parquet` and `cells_series/`. They are enough for the backend to load every
  region. Everything else under `pipeline/data/` regenerates from FIRMS (the downloader needs a FIRMS
  MAP_KEY in `pipeline/.env`, never committed).
- **Frozen ratios.** Tag `v1.0-data` marks them (`pipeline/docs/FINAL_RATIOS.md`).
- **Docker.** `docker compose up` mounts `pipeline/data/export` into the API container.
