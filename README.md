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
export/export/{region}/   harmonized data (data contract v0.4, made by the firecal pipeline)
        │  python -m firecal_api.cli ingest   (checks every contract rule, then loads)
        ▼
PostgreSQL ──► backend/ (FastAPI) ──► web/ (React + MapLibre + ECharts, also an Electron app)
```

| folder | what |
|---|---|
| [`data_contract.md`](data_contract.md) | units, flags and rules of the exported data |
| [`export/export/`](export/export) | the exports for `lebanon`, `greece`, `eastmed` |
| [`backend/`](backend/README.md) | database, ingest, API, accounts, alerts, tests |
| [`web/`](web/README.md) | the website / desktop app |
| [`infra/azure/`](infra/azure) | one-time setup for GitHub → Azure deploys |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | branches, pull requests, how deploys work |

## Run it locally

**With Docker** (database, API and website in one go; loads the exports on first start):

```sh
cp .env.example .env        # optional settings (Google sign-in, email); works as is
docker compose up --build   # website http://localhost:5173 · API http://localhost:8010/docs
```

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
