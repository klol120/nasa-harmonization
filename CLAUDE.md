# CLAUDE.md — MODIS/VIIRS burning-activity calendar (NASA Space Apps 2026)

Status: **All phases done and merged to `main` (81 tests), 2026-11-12. See docs/reports/WHILE_YOU_WERE_AWAY.md.**

## Working rules
- Work in phases and stop after each one for review. Phase 4 must not continue until every difference from the
  PDF is explained.
- `FIRMS_MAP_KEY` lives only in `.env` (gitignored). Never print, log or commit it. `tools/download_firms.py`
  redacts it from logs and exceptions.
- Use the Python in `.venv/` (`.venv/bin/python`, `.venv/bin/pytest`). The system Python's numpy is broken.
- Every choice goes in `config.yaml`; code takes no magic constants. Check real column names in `data/raw/`
  before assuming them.
- The method is in `docs/methods.pdf`. Its section numbers are used below.

## Method summary (docs/methods.pdf)
1. **Common unit.** A fire-day is a 0.05° cell with at least one detection on a UTC day.
   N_s(r,y,m) = Σ cells, days F_s(c,d).
2. **Terra-only correction.** Before 2002-07-04 MODIS is Terra only. Scale by
   kT(m) = Σ_y N_T∪A / Σ_y N_T over 2003–2020.
3. **Monthly calibration.** On the overlap O = 2012–2020, a_m = Σ N_V / Σ N_M (a ratio of sums), and
   Ñ_V = a_m · N_M.
4. **ML backcast.** Optional, out of scope unless it beats step 3 on hold-out.
5. **Splice.** H = Ñ_V before 2012-01-20 and N_V after. A year bootstrap over O gives a 90% band.

Validation: hold-out (fit 2012–16, test 2017–20; WAPE, bias), continuity at 2012, and break checks at the MODIS
processing changes (2018, 2023).

## Findings so far that shape the design

### Greece already reproduces Table 1 with plain cleaning
Plain cleaning means `type == 0`, nominal/high confidence, exact duplicates dropped, and nothing else.

| 2012–2020, VIIRS/MODIS | PDF | ours |
|---|---|---|
| detections (cleaned) | 3.41 | 3.40 |
| fire-days 0.01° | 2.63 | 2.63 |
| fire-days 0.05° | 2.86 | 2.86 |
| fire-days 0.10° | 2.89 | 2.88 |

- The PDF's cleaned totals are full-record figures, not 2012–2020. MODIS 2000–2025 gives 43,623 (PDF 43,623)
  and VIIRS 2012–2025 gives 70,197 (PDF 70,195; the 2-detection difference is open and goes to Phase 4).
- The PDF's "persistent industrial sources (94% night, mean FRP 1.3 MW)" match the VIIRS `type == 2` rows
  (97% night, 1.36 MW). The `type` column already does that exclusion. The empirical persistence filter
  is still needed for inputs without `type` (FIRMS NRT CSVs), so its mode is `auto` (see clean).

### Lebanon is thin and has a very different ratio
Preliminary, with the same plain cleaning, 2012–2020:

| VIIRS/MODIS | Greece | Lebanon |
|---|---|---|
| raw detections (all rows) | 4.35 | 8.88 |
| cleaned detections | 3.40 | 6.75 |
| fire-days 0.05° | **2.86** | **6.34** |

Lebanon fire-days per calendar month, summed over 2012–2020 (MODIS = Terra ∪ Aqua):

| month | MODIS | VIIRS | years with MODIS > 0 (of 9) | local a_m |
|---|---|---|---|---|
| Jan | 3 | 52 | 2 | 17.3 |
| Feb | 2 | 69 | 2 | 34.5 |
| Mar | 3 | 103 | 3 | 34.3 |
| Apr | 4 | 130 | 2 | 32.5 |
| May | 5 | 167 | 3 | 33.4 |
| Jun | 27 | 305 | 9 | 11.3 |
| Jul | 57 | 484 | 9 | 8.5 |
| Aug | 66 | 442 | 9 | 6.7 |
| Sep | 117 | 549 | 9 | 4.7 |
| Oct | 133 | 462 | 9 | 3.5 |
| Nov | 53 | 203 | 7 | 3.8 |
| Dec | 10 | 78 | 4 | 7.8 |
| **total** | **480** | **3044** | | **6.34** |

- **Dec–May need donor borrowing.** There are 2–10 MODIS fire-days in 9 years, and MODIS sees fire in only
  2–4 of the 9 years, so a local a_m is noise.
- **Jun–Nov have enough local signal** for a blend.
- **The ratio is 2.2× Greece's.** That fits the PDF's explanation (VIIRS gains most on small, cool
  agricultural burns), but it's worth checking against donors in Phase 5.

### Outages
Zero-detection runs over Greece+EastMed include known outages: Terra 2001-06-15→07-02 and
2016-02-19→27, and S-NPP 2022-07-27→08-10. Winter zero runs are normal for MODIS, so gap detection
needs a statistical test plus a reviewed list (see clean).

## Repo layout

```
config.yaml                 every choice (regions, grid, sensors, years, donors, strategies)
pyproject.toml              package `firecal`, pytest config
src/firecal/
  config.py                 load + validate config.yaml; resolve paths per region/stage
  schema.py                 internal detection schema, cell-month schema, export contract; validators
  geo.py                    cell_id <-> lat/lon, country tagging (moved from tools/footprint.py)
  io.py                     read_stage(region, stage) / write_stage(...) for Parquet + JSON sidecars
  adapters/
    __init__.py             registry, format auto-detection by header signature
    firms_csv.py            FIRMS archive CSV, area-API CSV, NRT CSV (one parser, three variants)
    shapefile.py            FIRMS archive/NRT shapefile (10-char uppercase DBF names)
    json_.py                FIRMS JSON records and GeoJSON features
    generic.py              any CSV via a column_map in config
  calibration.py            strategies (single, local, donor, pooled, blend) + year bootstrap; pure functions
  metrics.py                WAPE, bias, continuity statistics
  stages/
    ingest.py clean.py grid.py terra.py calibrate.py validate.py splice.py anomalies.py export.py
  cli.py                    python -m firecal <stage>|all --region R [--force]
tools/
  download_firms.py         Phase 0 downloader (unchanged)
  footprint.py              thin wrapper over firecal.geo.tag_country
tests/
  synthetic.py              FIRMS-shaped CSV generator with a known true ratio (tests only)
  fixtures/                 a few real rows per format, copied from data/raw (no key)
  test_*.py                 one per module/stage + test_export_contract.py
data/
  raw/                      Phase 0 output (read-only)
  ext/                      external reference data (Natural Earth)
  interim/{region}/         ingest, clean, grid, terra outputs
  processed/{region}/       calibrate, validate, splice, anomalies outputs
  export/{region}/          frontend files (contract: docs/data_contract.md)
docs/
  methods.pdf  data_contract.md  reports/{region}_validation.md
```

## Stages
Each stage reads the previous stage's files and writes its own, and can be rerun alone.

| stage | reads | writes (per region) |
|---|---|---|
| ingest | `inputs` in config → adapters | `interim/{r}/detections.parquet`, `ingest_report.json` |
| clean | detections | `interim/{r}/detections_clean.parquet`, `clean_report.json`, `persistent_sources.parquet`, `outages.parquet` |
| grid | clean, outages | `interim/{r}/fire_segments.parquet` |
| terra | fire_segments | `interim/{r}/kT.parquet`, `kT_boot.parquet` |
| calibrate | fire_segments (+ donor regions'), kT | `processed/{r}/factors.parquet`, `factors_boot.parquet` |
| validate | fire_segments, factors | `processed/{r}/holdout.parquet`, `continuity.json`, `breaks.parquet`, `docs/reports/{r}_validation.md` |
| splice | fire_segments, kT, factors, outages | `processed/{r}/harmonized.parquet` |
| anomalies | harmonized | `processed/{r}/anomalies.parquet`, `baseline.parquet` |
| export | anomalies, factors, kT, holdout | `export/{r}/calendar.parquet`, `calendar.csv.gz`, `region_monthly.{csv,json}`, `cells.json`, `cells.geojson`, `meta.json` |

- A stage skips work when its output is newer than its inputs and config, unless `--force` is given.
- Each output's JSON sidecar records the config hash, inputs and row counts.
- **Donor dependency.** Lebanon's calibrate reads `interim/eastmed/fire_segments.parquet`. `firecal all
  --region lebanon` runs eastmed through `grid` first.

### ingest
- Each config `inputs` entry says {path glob, format, source, origin}. `format: auto` sniffs the header.
- Adapters return the internal schema, which is validated in `schema.py`.
- Country comes from the file when present (archives). Otherwise `geo.tag_country` sets it (API, NRT,
  shapefile, JSON).
- Rows outside the region's `countries` or bbox are dropped, so every year uses the same footprint
  (Phase 0 rule).

### clean
Applied in this order; `clean_report.json` counts the rows removed by each rule.
1. `fire_type == 0`. Rows with NA type (NRT) are kept here and handled by rule 4.
2. Satellites in config (Terra, Aqua, SNPP).
3. `confidence_class` in config (nominal, high).
4. **Duplicates.** Exact (lat, lon, datetime_utc, satellite) duplicates are dropped. When the same detection
   comes from both SP and NRT, SP is preferred (`origin_priority`).
5. **Persistent sources, `mode: auto`.**
   - Rows with a `type` column rely on `type == 0`.
   - Rows without it use the empirical filter. A 0.01° cell is persistent if it is detected in at least
     `min_year_frac` of the years and at least `min_night_frac` of its detections are at night.
   - Flagged cells are written to `persistent_sources.parquet` for review.
   - `mode: always` applies the empirical filter on top of `type`; `off` disables it.
6. **Outages → `outages.parquet`** (satellite, date, reason).
   - Confirmed outages come from config `gaps.known`.
   - Suspects come from a test: a satellite-day with zero detections over `gaps.reference_regions` (Greece +
     EastMed) where P(0 | Poisson λ) < `gaps.p_threshold`. λ is a centred 31-day median of that
     satellite's daily counts.
   - Suspects are listed for review and flagged only when `gaps.use_suspects: true`. Never filled.

### grid
- `cell_id` = `"{row}_{col}"` with row = floor((lat+90)/g) and col = floor((lon+180)/g), g = 0.05.
  It is global and region-independent, so Lebanon's cells are the same cells inside EastMed.
  The floor uses a 1e-9 guard against float error at cell edges.
- A fire-day is (cell, UTC date, sensor) with at least one detection. MODIS fire-days are Terra ∪ Aqua.
  A Terra-only flag is kept for kT.
- **Output `fire_segments`** has one row per (cell_id, country, year, month, segment) with n_modis,
  n_terra, n_viirs, and gap_days_{terra,aqua,snpp}.
- **Segments** split a month at the config boundaries that fall inside it: 2002-07-04 (Terra-only cutoff)
  and 2012-01-20 (VIIRS start). This gives an exact day-level treatment of July 2002 and January 2012. All
  other months have a single segment.
- **Why country is kept.** A border cell can have detections from two countries, and donor groups filter
  by country.

### terra
- kT(m) = Σ_y N_T∪A / Σ_y N_T over `terra.fit_years` (2003–2020), at region level, per calendar month.
- It uses the same strategy machinery as calibration (local/donor/pooled/blend), because Lebanon's winter
  Terra counts are also thin.
- A year bootstrap gives `kT_boot.parquet`.
- Applied to MODIS counts in segments ending before 2002-07-04.

### calibrate
For each (strategy, calendar month), a_m comes from fire-day sums over `overlap_years`. Only segments where
both sensors are available count. For January 2012 that means MODIS days ≥ 01-20 only.

| strategy | a_m |
|---|---|
| `single` | one ratio Σ N_V / Σ N_M over all months (the PDF baseline) |
| `local` | ratio of local sums |
| `donor:<group>` | ratio of the donor group's sums (country filter on its region) |
| `pooled:<group>` | ratio of (local + donor) sums |
| `blend:<group>` | log a_m = w_m log a_local + (1−w_m) log a_donor, with w_m = n_m / (n_m + k) and n_m = local MODIS fire-days in month m; w_m = 0 when n_m = 0 |

- **Donor groups** (config): cyprus [Cyprus], southern_turkey [Turkey ∩ EastMed bbox], syria [Syria],
  israel_palestine [Israel, Palestine], eastmed_pool [all five]. Optionally greece [Greece].
  Donors never include the local region's own country.
- **k** is chosen from `calibration.blend_k_grid` by hold-out WAPE and reported. That choice is made on
  the fit years only, by a nested split, so the hold-out stays honest.
- **Bootstrap.** B = 1000 resamples of overlap years with replacement. The same years are drawn for local
  and donor, and the factors are recomputed. Bands are the 5th and 95th percentiles. kT and a_m bootstrap
  independently and the draws are multiplied.
- The strategy used downstream is `calibration.strategy`, set per region in config. It is chosen by a
  human from the validation table, not automatically.

### validate
- **Hold-out** for every strategy: fit 2012–16, test 2017–20, on region monthly totals.
  WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. The reverse fold (fit 17–20, test 12–16) is
  reported as a robustness column. Also a per-month breakdown, and r of monthly log counts (PDF: 0.95).
- **Continuity at 2012.** Mean harmonized annual total for 2009–2011 (estimates) vs 2012–2014 (observed),
  with the bootstrap band. On the overlap years, Σ Ñ_V / Σ N_V per year should be about 1. A step is
  flagged when the ratio falls outside the band.
- **Breaks.** The annual N_V/N_M ratio for 2012–2025, annotated with MODIS `version`. Shifts after 2018
  and 2023 are flagged against the overlap bootstrap range. Report only.
- Writes `docs/reports/{r}_validation.md` with all tables.

### splice
Per cell and month, the segments are combined:
- Segments before 2012-01-20: harmonized = a_m · kT(m)^[Terra-only] · n_modis (estimate).
- Segments after: harmonized = n_viirs (observed).
- Bands: low/high use the bootstrap factor percentiles. For observed segments low = high = value.
- is_estimate = any estimated segment in the month. January 2012 is mixed and flagged as an estimate.
- has_gap = at least one outage day for a satellite feeding that month's harmonized value.
- data_available = the feeding sensor has data for the whole month (false after the SP max_date).
  Values are null when false, never 0.

### anomalies
- Baseline per cell and calendar month = mean and sd of harmonized over `anomalies.baseline_years`
  (2001–2025).
- z = (H − mean) / max(sd, `min_sd`). z is null when sd = 0 and `min_sd` = 0.
- The same is computed for region totals.
- **2026 is display-only.** It is excluded from the baseline, and its z is computed against the
  2001–2025 baseline. z is null where `data_available` is false.
- A sensitivity run on the 2012–2025 baseline is reported by validate.

### export
See `docs/data_contract.md`.

## Internal schema (`detections*.parquet`)

| column | type | notes |
|---|---|---|
| lat, lon | float64 | WGS84 |
| datetime_utc | timestamp[us, UTC] | acq_date + acq_time (HHMM, zero-padded; API omits padding) |
| sensor | category {MODIS, VIIRS} | from `instrument` |
| satellite | category {Terra, Aqua, SNPP, NOAA20, NOAA21} | `Terra`/`T`, `Aqua`/`A`, `N`/`Suomi NPP` → SNPP, `N20` → NOAA20, `N21` → NOAA21 |
| confidence_class | category {low, nominal, high} | VIIRS l/n/h; MODIS 0–29 low, 30–79 nominal, 80–100 high (FIRMS user guide) |
| confidence_raw | string | original value |
| frp | float32 | MW |
| daynight | category {D, N} | |
| fire_type | Int8 (nullable) | 0 vegetation, 1 volcano, 2 static land, 3 offshore; NA for NRT |
| version | string | e.g. `6.03`, `61.03`, `2`, `2.0NRT`; kept for break checks |
| country | string | archive file name, or Natural Earth tag |
| source | category | MODIS_SP, VIIRS_SNPP_SP, MODIS_NRT, … |
| origin | category {archive, api, nrt, shapefile, json, generic} | |
| input_file | string | relative path, for traceability |

Brightness, scan and track are dropped (not used by the method).

**Observed raw columns** (Phase 0, archive = API):
- MODIS: `latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite, instrument,
  confidence, version, bright_t31, frp, daynight, type`
- VIIRS: the same with `bright_ti4/bright_ti5`.
- Region files add `country`.
- NRT, shapefile and JSON layouts are from FIRMS documentation and will be confirmed on a real file at
  the hackathon:
  - NRT has no `type`.
  - Shapefile DBF names are uppercase.

## config.yaml (proposed full shape)

Phase 0 keys are kept, except that `regions.*.archive_countries` is renamed `countries` and the
downloader is updated to match.

```yaml
regions:
  lebanon: {bbox: [35.00, 33.00, 36.70, 34.75], countries: [Lebanon]}
  greece:  {bbox: [19.20, 34.70, 29.80, 41.80], countries: [Greece]}
  eastmed: {bbox: [30.00, 29.40, 42.40, 38.00], countries: [Lebanon, Syria, Israel, Palestine, Cyprus, Turkey]}
inputs:                      # per region; {region} is substituted
  - {path: "data/raw/{region}/MODIS_SP_[0-9][0-9][0-9][0-9].csv", format: firms_archive_csv, source: MODIS_SP}
  - {path: "data/raw/{region}/VIIRS_SNPP_SP_[0-9][0-9][0-9][0-9].csv", format: firms_archive_csv, source: VIIRS_SNPP_SP}
  - {path: "data/raw/{region}/*_2026_api.csv", format: firms_api_csv, source: auto}
grid: {size_deg: 0.05}
sensors:
  satellites: [Terra, Aqua, SNPP]
  terra_only_until: 2002-07-04      # Aqua MODIS data start
  viirs_start: 2012-01-20
clean:
  fire_types: [0]
  confidence_classes: [nominal, high]
  modis_confidence_bins: {low: [0, 29], nominal: [30, 79], high: [80, 100]}
  origin_priority: [archive, api, shapefile, json, generic, nrt]
  persistent: {mode: auto, cell_deg: 0.01, min_year_frac: 0.6, min_night_frac: 0.8}
gaps:
  reference_regions: [greece, eastmed]
  p_threshold: 0.001
  use_suspects: false
  known:                            # confirmed outages; reviewed list grows in Phase 2
    - {satellite: Terra, start: 2001-06-15, end: 2001-07-02}
    - {satellite: Terra, start: 2016-02-19, end: 2016-02-27}
    - {satellite: SNPP,  start: 2022-07-27, end: 2022-08-10}
terra: {fit_years: [2003, 2020], strategy: local}
calibration:
  overlap_years: [2012, 2020]
  holdout: {fit: [2012, 2016], test: [2017, 2020]}
  strategies: [single, local, "donor:*", "pooled:*", "blend:*"]
  strategy: {greece: local, lebanon: "blend:eastmed_pool", eastmed: local}   # set after Phase 4/5 review
  blend_k_grid: [0, 5, 10, 20, 50, 100, 1e9]
  bootstrap: {n: 1000, seed: 2026, ci: 0.90}
donors:
  cyprus:           {region: eastmed, countries: [Cyprus]}
  southern_turkey:  {region: eastmed, countries: [Turkey]}
  syria:            {region: eastmed, countries: [Syria]}
  israel_palestine: {region: eastmed, countries: [Israel, Palestine]}
  eastmed_pool:     {region: eastmed, countries: [Cyprus, Turkey, Syria, Israel, Palestine]}
years:
  stats_last_year: 2025             # 2026 partial: display only, excluded from calibration/baseline/anomaly stats
  display_last_month: 2026-12
anomalies: {baseline_years: [2001, 2025], sensitivity_baselines: [[2012, 2025]], min_sd: 0}
download: {...}                     # Phase 0 section, unchanged
```

## Testing (pytest)
- **Adapters:** one test per format on real fixture rows, plus synthetic shapefile and JSON. Covers schema
  dtypes, satellite and confidence mapping, and zero-padding of acq_time.
- **clean:** each rule removes exactly the planted rows; SP is preferred over NRT; auto mode switches on a
  missing `type`.
- **grid:** cell_id round-trips, edge points, clusters collapse to one fire-day, segment splits on
  2002-07-04 and 2012-01-20.
- **terra / calibrate:** `tests/synthetic.py` writes FIRMS-shaped CSVs from simulated fire-days with
  known per-month detection probabilities, a known Terra share, and VIIRS multi-pixel clusters. Calibration
  must recover the true a_m and kT within tolerance, and the 90% band must cover the truth in about 90% of
  seeds. The blend tends to local as n grows and to donor at n = 0.
- **validate:** WAPE and bias on a hand-computed example.
- **splice / anomalies:** January 2012 mixed month, null vs 0, the 2026 display-only rule.
- **test_export_contract.py:** the export matches `docs/data_contract.md` exactly (columns, dtypes,
  nullability, invariants).

## Decisions from the Phase 1 review
1. **2026 anomaly_z** is computed against the 2001–2025 baseline, for display only. It is null where
   `data_available` is false. A month the feeding sensor covers only partly (e.g. the current NRT month)
   has `partial_month = true`.
2. **Baseline** is 2001–2025, with a sensitivity run on 2012–2025 (`anomalies.sensitivity_baselines`).
   Validate reports how much z changes (correlation, mean |Δz|, share of cells whose |z|>2 status flips).
3. **Persistence filter** runs in `mode: auto`. On Lebanon it also runs as a diagnostic only. The report
   lists the top 20 cells by VIIRS fire-days (coordinates, years active, night share, FRP) for checking
   against known open waste-burning dump sites, plus the 2012–2020 fire-day ratio with those cells
   excluded. The cells are not removed by default.
4. **Exports** add JSON (`region_monthly.json`, `cells.geojson`) alongside Parquet and CSV.gz. The formats
   are pending confirmation from the frontend team.

## Decisions from the Phase 2 review
- `persistence.exclude_from_calibration: true` (default). Flagged fine cells are dropped when fitting kT
  and a_m, locally and in every donor region, each region using its own flagged list under the same rule.
  They stay in the displayed data. The export carries `is_persistent` so the frontend can show or hide
  them.
- The Greece reproduction check keeps the PDF's rules (`pdf_rules` variant). Validate reports the
  persistence rule as a separate line (`persistence_excluded`).
- `gaps.use_suspects` stays false. Suspects are listed in `docs/reports/outage_suspects.md` with
  `gaps.review_first` pinned at the top.

## Phase 3 implementation notes (where the design was refined)
- **grid** writes `fire_days` (one row per cell-day, with per-satellite flags, `*_np` flags without
  persistent-source detections, and the country of most of the cell-day's detections, so a border
  fire-day is counted once). It also writes `fire_segments` (cell × month × segment counts) and
  `segments` (the region-wide calendar with sensor-day availability and outage days).
- **Fitting inputs** (`fitting.py`, shared by terra, calibrate and validate):
  - only dates where every involved satellite has data;
  - flagged outage days removed for all sensors;
  - persistent fire-days removed when `exclude_from_calibration` is on.
- **Blend in linear form, not log:** a_m = (V_L + k a_D) / (M_L + k), i.e. w_m = M_L / (M_L + k). The
  log form is undefined for months with zero local VIIRS or MODIS fire-days, which is common in Lebanon's
  winter. k is chosen by leave-one-year-out WAPE. In validate's hold-out, k is chosen on the fit years
  only.
- **Continuity statistic:** step index = (H after / H before) / (MODIS after / MODIS before), with
  before = 2009–2011 and after = 2012–2014.
  - It is about 1 without an artificial step.
  - The band multiplies each a_m bootstrap draw by the year-to-year spread of observed/predicted VIIRS
    on the overlap. The factor bootstrap alone was too narrow and flagged Greece.
  - It is computed per variant with matching columns.

## Phases 4–5 (done while the user was away; see docs/reports/WHILE_YOU_WERE_AWAY.md)
- **Pipeline:** ingest → clean → grid → terra → calibrate → validate → splice → anomalies → export
  (`python -m firecal all --region R`).
- **Strategies:**
  - Calibration: Lebanon uses `single`, the top-ranked in `tools/lebanon_experiment.py`. Greece and
    EastMed use `local`.
  - kT: Lebanon uses `single`; the others use `local`.
  - All alternatives, including affine `affine_local`, `affine_blend:G` and `affine_blend_a:G`, can be
    selected in config.
- **Affine intercept:** b is spread over cells by each cell's share of overlap VIIRS fire-days in that
  calendar month. The donor b is scaled by footprint cell counts.
- **low_confidence:** `config.low_confidence`, applied per calendar month to estimated months.
- **Export contract:** 0.2 (`docs/data_contract.md`).
- **Git:** `main` holds Phases 0–3. The Phase 4–5 work is on `autonomous-phase4-5`. data/ is not
  tracked, except the manifest.

## Second autonomous session (2026-11-12)
- **Per-region settings:** `by_region` overrides work in `low_confidence` and `anomalies`
  (`config.region_settings`).
  - Lebanon: 80% zero-MODIS share and a 2012–2025 baseline.
  - Greece and EastMed: 95% and a 2001–2025 baseline.
- **Composite strategies** (`calibration.composites`): the monthly shape comes from `shape` and each
  year's estimated total from `level`. Lebanon's default is `affine_shape_single_level`
  (shape `affine_blend:cyprus`, level `single`).
- **Config overrides:** a key ending in `!` replaces a section instead of merging it. Test configs use
  `regions!` and `donors!`.
- **Shared exports** are whitelisted in .gitignore: everything for Lebanon, all region_monthly.json,
  and cells.geojson files under 5 MB.
- **`tools/preview/`** is the static export preview (sanity check only).

## Contract 0.4 and pool shape (2026-11-12)
- **Lebanon default:** `affine_shape_single_level_pool` (shape from `affine_blend:eastmed_pool`). See
  docs/reports/lebanon_robustness.md.
- **Export 0.4:**
  - per-cell values only in the calendar;
  - region-wide flags only in region_monthly;
  - `ym` on every table;
  - `cells_series/{year}.json` for maps;
  - `cells.json` dropped.

  The contract is docs/data_contract.md; the preview in tools/preview uses it.
