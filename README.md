# Wel3a · Burning Calendar

NASA Space Apps 2026, challenge #09: one consistent record of burning activity from MODIS and VIIRS
satellite fire detections, for Lebanon, Greece and the Eastern Mediterranean (2000 to today).

MODIS sees roughly 3–6× fewer fire-days than VIIRS, so a naive record jumps when VIIRS starts in 2012.
Wel3a converts everything to **VIIRS-equivalent fire-days**, so a change of satellite never looks like a
fire crisis, and shows the result as a month × year burning calendar, a map, anomalies and season charts.

**Live:** https://wel3a-web.blackwave-481696ae.francecentral.azurecontainerapps.io ·
API docs: https://wel3a-api.blackwave-481696ae.francecentral.azurecontainerapps.io/docs

## How it fits together

```
pipeline/  python -m firecal all --region R      ->  pipeline/data/export/{region}/  (data contract 0.5)
backend/   python -m firecal_api.cli ingest       <-  pipeline/data/export (default EXPORT_DIR)
           (checks every contract rule, then loads into PostgreSQL)
web/       VITE_API_URL=http://127.0.0.1:8000     <-  backend API
```

| folder | what | read first |
|---|---|---|
| [`pipeline/`](pipeline/) | **firecal**, the harmonization pipeline. FIRMS download → cleaning → 0.05° fire-days → MODIS→VIIRS calibration (monthly ratios, Terra-only correction, NOAA-20 continuation) → splice → anomalies → export. Also `python -m firecal add-country <Country>`. | `pipeline/CLAUDE.md`, `pipeline/docs/FINAL_RATIOS.md` |
| [`data_contract.md`](data_contract.md) | units, flags and rules of the exported data | |
| [`backend/`](backend/README.md) | FastAPI + PostgreSQL: database, ingest, API, accounts, alerts, tests | `backend/README.md` |
| [`web/`](web/README.md) | the website / desktop app (React + MapLibre + ECharts, also an Electron app); reads only the backend API | `web/README.md` |
| [`infra/azure/`](infra/azure) | one-time setup for GitHub → Azure deploys | |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | branches, pull requests, how deploys work | |

- **Shared exports.** The exports in git are `pipeline/data/export/*`: `meta.json`, `region_monthly.json`,
  `cells.geojson`, `calendar.parquet` and `cells_series/`. They are enough for the backend to load every
  region. Everything else under `pipeline/data/` regenerates from FIRMS (the downloader needs a FIRMS
  MAP_KEY in `pipeline/.env`, never committed).
- **Frozen ratios.** Tag `v1.0-data` marks them (`pipeline/docs/FINAL_RATIOS.md`).

## Run it locally

**With Docker** (pipeline, database, API and website in one go):

```sh
cp .env.example .env        # optional settings (FIRMS key, Google sign-in, email); works as is
docker compose up --build   # website http://localhost:5173 · API http://localhost:8010/docs
```

What happens on every `docker compose up`:

```
pipeline-seed  copies the exports committed in git into the `pipeline-data` volume (seconds)
     ├─► api       loads them and serves the website right away
     └─► pipeline  NASA FIRMS up to yesterday → every region recomputed → new exports in the volume
                   → writes pipeline_status.json → the api sees it and loads the new releases (no restart)
```

- The pipeline needs `FIRMS_MAP_KEY` in `.env` ([free key](https://firms.modaps.eosdis.nasa.gov/api/map_key/)).
  Without it, or with `PIPELINE_RUN=0`, the site serves the committed exports.
- The **first run** downloads every FIRMS archive (2000–2025) and this year's data through the area API: about
  an hour. Downloads stay in the volume, so later runs fetch only the new days and then recompute.
- `config.yaml`'s `coverage` is extended to what FIRMS reports as available (inside the container only), so
  new months show up as data, not as "no data". S-NPP stays capped at the day it stopped sending data.
- Follow it with `docker compose logs -f pipeline`; the last run's summary is `pipeline_status.json` in the volume.
- `docker compose down -v` deletes the volume (and the database): the next start downloads everything again.

**Without Docker** (needs PostgreSQL, [uv](https://docs.astral.sh/uv/) and Node 22):

```sh
cd backend && cp .env.example .env    # set DATABASE_URL
uv run python -m firecal_api.cli init && uv run python -m firecal_api.cli ingest
uv run python -m firecal_api.cli serve           # http://127.0.0.1:8000
cd ../web && npm ci && npm run dev               # http://localhost:5173
```

## Optional accounts

Nothing is behind a login. Signing in (Google) adds **saved areas**, **email alerts** when an area's month is
unusually high, and the **monthly digest**; the email list also works without an account. Settings are
listed in [`backend/.env.example`](backend/.env.example) and explained in the
[backend README](backend/README.md#accounts-email-list-and-alerts-optional).

## Deploying

Work on `dev`, open a pull request into `main`; merging into `main` deploys to Azure automatically.
Details in [CONTRIBUTING.md](CONTRIBUTING.md).
