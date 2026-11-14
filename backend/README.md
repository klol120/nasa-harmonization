# Burning-calendar backend

PostgreSQL database and FastAPI service for the `firecal export` output described in
[`../data_contract.md`](../data_contract.md) (contract **v0.4**). Any region folder shaped like
`export/export/{region}/` can be loaded; nothing is specific to Lebanon, Greece or EastMed.

## Setup

```sh
cd backend
cp .env.example .env         # then put the PostgreSQL password in DATABASE_URL
uv sync
uv run python -m firecal_api.cli init      # creates the "firecal" database and the schema
uv run python -m firecal_api.cli ingest    # loads every region under EXPORT_DIR
uv run python -m firecal_api.cli serve     # API on http://127.0.0.1:8000, docs at /docs
```

On this machine, use `python -m …` rather than the `firecal-db` / `pytest` launchers: Windows
Application Control blocks those generated .exe files. It also blocks pandas, pyarrow and psycopg's
binary build, so the backend avoids them. It loads `calendar.csv.gz` into PostgreSQL with COPY. numpy,
scikit-learn, polars and DuckDB do load.

## How new exports arrive

Each `ingest` of a region folder becomes a **release**:

1. The files are checked against the contract: required files, `contract_version`, one region_monthly
   row per month, the cell_id/row/col formula, cell geometry, and the meta counts.
2. In **one transaction**, cells, region_monthly and the calendar are loaded, and then every contract
   invariant is checked in SQL:
   - `low ≤ harmonized ≤ high`;
   - harmonized is null iff `data_available` is false;
   - `harmonized == viirs_raw` in observed months;
   - `viirs_raw` is null before 2012;
   - (cell, ym) is unique and the calendar is complete;
   - region totals equal the sum over cells;
   - every `cells_series` file equals the calendar, including the rule for omitted cells.
3. If anything fails, the export is **rejected and nothing is written**. Otherwise it becomes the
   region's current release.

The previous release stays in the database: `releases` lists them, `set-current <id>` rolls back, and
`delete-release <id>` removes one. Loading the same export twice is a no-op unless you pass `--force`.

## Schema (`firecal_api/sql/001_init.sql`)

| table | rows | content |
|---|---|---|
| `region`, `release` | per region / per export | the full `meta.json` (jsonb), bbox, months, baseline years, `is_current` |
| `cell` | global 0.05° grid | `cell_key = row*7200 + col`, `cell_id`, centre, countries; shared by all regions |
| `release_cell` | cells of a release | `is_persistent` |
| `region_month` | per month | region totals and **all region-wide flags** |
| `cell_month` | per cell × month | modis_raw, viirs_raw, harmonized + band, anomaly_z (about 7M rows for all 3 regions) |
| `calibration_factor` | 12 per model | `meta.calibration.factors` (and the composite `shape` factors) |
| `model_run`, `prediction_region_month`, `prediction_cell_month` | ML output | see below |
| view `ml_cell_month` | | training table: cell values + region flags + cell attributes, current releases |

New migrations go in `firecal_api/sql/` as `002_….sql`. `init` (and `ingest`) apply any not yet applied.

## API

All region endpoints use the current release; add `?release=<id>` for another. Responses follow the
contract's shapes, so the frontend can use the API and the export files interchangeably.

| endpoint | returns |
|---|---|
| `GET /regions` | current release per region |
| `GET /regions/{r}/releases` | all releases of a region |
| `GET /regions/{r}/meta` | `meta.json` plus a `release` block |
| `GET /regions/{r}/monthly[?format=csv]` | `region_monthly` |
| `GET /regions/{r}/cells` | `cells.geojson` |
| `GET /regions/{r}/series/{year}` | `cells_series/{year}.json` (same content as the file; cached) |
| `GET /regions/{r}/calendar?cell_id=…&from=YYYY-MM&to=YYYY-MM[&format=csv]` | calendar rows; JSON is capped at 100k rows, CSV streams any size |
| `POST /regions/{r}/aggregate` | monthly sums over an area (`cell_ids`, `bbox`, GeoJSON `polygon`, `exclude_persistent`, `from`/`to`), with bands, recomputed z and flags |
| `GET /regions/{r}/model-runs`, `GET /regions/{r}/predictions` | ML runs and their predictions |
| `GET /regions/{r}/weather[?from=YYYY-MM&to=YYYY-MM]` | monthly past weather with each field's normal, `_anom`, `_z` and `precip_pct_of_normal`; `available: false` until fetched |

**Aggregation** follows the contract:
- Counts and bands are summed.
- `anomaly_z` is recomputed from the summed series against the region's baseline years. It uses
  months with `display_only = false` and the **sample** standard deviation (n−1), which reproduces the
  exported region z exactly.
- A cell belongs to a polygon or bbox when its centre is inside it.
- Region totals include persistent cells. `exclude_persistent` drops them and recomputes the z.

## Weather (Meteomatics, `firecal_api/weather.py`)

Past weather is context for the fire calendar, not a forecast. It is fetched once and stored, so the
website never calls Meteomatics and the credentials never leave the server.

- **Where:** the region's bbox is split 3×3. Each tile with fires gives one point: its busiest non-persistent
  cell, weighted by the tile's share of fire-days. The points are chosen on the first fetch and kept
  (`weather_region`).
- **What:** daily `t_mean_2m_24h:C`, `t_max_2m_24h:C`, `precip_24h:mm`, `wind_speed_mean_10m_24h:ms` and
  `relative_humidity_mean_2m_24h:p`, averaged over the points and stored per month (`weather_month`; rain is a
  monthly total). Months with missing days are marked `complete: false` and get no anomaly.
- **Normals** are the mean (and sample sd, for z) of the same calendar month over the release's baseline years.
- **Budget:** one request covers every point and field for 12 months, so 2000-2026 is ~27 requests per region.
  Requests are counted in `meteomatics_usage`, and a fetch stops at `METEOMATICS_DAILY_CAP` (default 800) per UTC day.
  Re-running only fetches months that are missing, or recent months that have new days.

```sh
python -m firecal_api.cli weather-check            # 1 request: test credentials and parameters
python -m firecal_api.cli weather-fetch --dry-run  # what would be fetched
python -m firecal_api.cli weather-fetch            # fetch it (also runs on Docker start when credentials are set)
python -m firecal_api.cli weather-export DIR       # <region>.json, to move data without re-fetching
python -m firecal_api.cli weather-import DIR       # (Docker loads /data/weather on start)
```

If a parameter isn't in the account's package, `--fields t_mean_c,precip_mm` limits the fetch to the given fields.

## Machine learning

- **Train** from the `ml_cell_month` view, for example with polars:
  `pl.read_database_uri("select * from ml_cell_month where region_id = 'lebanon'", DATABASE_URL)`.
- **Write** results with `firecal_api.ml.save_run(...)`. It records the run against the release it was
  trained on, together with its params, metrics and artifact path, and stores region-level and/or
  cell-level predictions.
- **Read** them back from `/regions/{r}/predictions`.

Predictions use the units of the target (VIIRS-equivalent fire-days for `harmonized`). Keep MODIS units
separate, as the contract requires.

## Tests

```sh
uv run python -m pytest -q
```

- `test_contract_files.py` needs only the export files.
- `test_db_api.py` loads Lebanon into a separate `<db>_test` database (dropped and recreated on each
  run) and checks that the API reproduces `region_monthly.json`, `cells.geojson` and the
  `cells_series` files. It also checks that whole-region aggregation reproduces the exported z, and
  that a broken export is rejected without writing anything.

## Accounts, email list and alerts (optional)

None of this gates the data: every region endpoint stays public. Settings are in `.env.example`.

| endpoint | does |
|---|---|
| `GET /auth/config` | which sign-in methods exist (Google client id, local test sign-in) |
| `POST /auth/google` | exchange a Google ID token for a session token (`Authorization: Bearer …`) |
| `POST /auth/dev-login` | local test sign-in, only with `AUTH_DEV_LOGIN=1` |
| `GET /auth/me`, `POST /auth/logout`, `DELETE /me` | session, sign out, delete account |
| `POST /newsletter/subscribe`, `GET /newsletter/confirm`, `GET /newsletter/unsubscribe` | email list with double opt-in |
| `GET/POST /me/areas`, `PATCH/DELETE /me/areas/{id}` | saved areas with their latest month and alert settings |
| `GET /admin/stats` | counts for `ADMIN_EMAILS` |
| `GET /dev/outbox` | the emails that would have been sent (only with `AUTH_DEV_LOGIN=1`) |

Scheduled jobs (cron, or a Container Apps job):

```sh
uv run python -m firecal_api.cli send-alerts    # daily: email saved areas whose newest month is unusual (once per month)
uv run python -m firecal_api.cli send-digest    # monthly: digest for confirmed subscribers
uv run python -m firecal_api.cli send-outbox    # send queued emails over SMTP (also done right after each job)
```
