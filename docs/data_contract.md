# Data contract: burning-activity calendar export

Version 0.2 (draft, 2026-11-12). Producer: `firecal export`. Consumer: the frontend team (browser app).

Changes from 0.1:
- Added `low_confidence` and `is_persistent` to the calendar.
- Added `n_persistent_cells` to region_monthly.
- Added `is_persistent` to cells.
- Added `low_confidence_rule`, `formats_status`, the affine intercept `b` and both continuity bands to meta.

> **The formats are pending confirmation from the frontend team.** Parquet, CSV.gz and JSON are all
> produced. Tell us which ones you'll use.

## Files
All files live in `data/export/{region}/`, where `{region}` is one of `lebanon`, `greece`, `eastmed`.

| file | content |
|---|---|
| `calendar.parquet` | one row per cell per month (canonical) |
| `calendar.csv.gz` | the same rows as CSV (UTF-8, header, `,` separator, empty field = null) |
| `region_monthly.csv` | one row per month: region totals, with the same columns minus `cell_id` |
| `region_monthly.json` | the same rows as a JSON array of objects (null = JSON `null`) |
| `cells.json` | grid cell attributes (and bounds) |
| `cells.geojson` | the same cells as a GeoJSON FeatureCollection of polygons; properties as in cells.json |
| `meta.json` | units, dates, calibration factors, validation summary, caveats |

**Compatibility rules**
- New columns or keys may be added in a minor version, so ignore any you don't know.
- Renaming or removing a field, or changing a type, needs a major version bump. `meta.json` carries
  `contract_version`.

## Units
Every count is in **fire-days**. A fire-day is one 0.05° cell with at least one active-fire detection on
one UTC day, so a cell-month value is between 0 and the number of days in the month. `harmonized` is in
**VIIRS-equivalent fire-days**. Fire-days measure burning activity, not burned area.

## calendar (one row per `cell_id` × `year` × `month`)

Rows cover every cell in `cells.json` and every month from `meta.time.first_month` (2000-11) to
`meta.time.last_month` (2026-12), including months with no data. A missing row never means zero.

| column | type | null? | meaning |
|---|---|---|---|
| `cell_id` | string | no | grid cell, see cells.json |
| `year` | int16 | no | |
| `month` | int8 | no | 1–12 |
| `modis_raw` | int16 | yes | MODIS (Terra ∪ Aqua) fire-days, no corrections. Null when MODIS has no data for the month. |
| `viirs_raw` | int16 | yes | VIIRS S-NPP fire-days. Null before 2012-01. January 2012 counts days ≥ 2012-01-20 only. |
| `harmonized` | float32 | yes | VIIRS-equivalent fire-days. Estimated from MODIS before 2012-01-20, observed VIIRS after. Null iff `data_available` is false. |
| `harmonized_low` | float32 | yes | lower bound of the 90% band. Equals `harmonized` when `is_estimate` is false. |
| `harmonized_high` | float32 | yes | upper bound of the 90% band. Equals `harmonized` when `is_estimate` is false. |
| `is_estimate` | bool | no | true if any part of the month is estimated from MODIS (all months ≤ 2011-12, plus 2012-01). The UI must label these as estimates. |
| `has_gap` | bool | no | at least one satellite-outage day in the month for a sensor feeding `harmonized`. The value is a lower bound, because outage days are never filled. |
| `data_available` | bool | no | false when the feeding sensor has no data for the month (e.g. 2026 months after the last standard-processing date). All value columns are then null: show "no data", not 0. |
| `display_only` | bool | no | true for rows excluded from calibration, baselines and anomaly statistics (all of 2026, a partial year). |
| `partial_month` | bool | no | true when `data_available` is true but the feeding sensor covers only part of the month (e.g. the current month in near-real-time data). The value is not comparable to full months; show it as partial. |
| `low_confidence` | bool | no | true for estimated months (`is_estimate`) whose calendar month fails the low-confidence rule in `meta.low_confidence_rule`. On the overlap years, the local region either has fewer than `min_modis_fire_days` MODIS fire-days in that calendar month, or at least `max_zero_modis_share` of its VIIRS fire-days fall in cell-days without any MODIS detection. Show these with extra caution. Always false for observed months. |
| `is_persistent` | bool | no | the cell contains a persistent source (industrial site or open waste burning: detected in most years, mostly at night). Constant per cell, also in cells.json. These cells are excluded when fitting the calibration but kept in the data; the UI may show or hide them. |
| `anomaly_z` | float32 | yes | (harmonized − baseline mean) / baseline sd for this cell and calendar month (baseline years in `meta.anomalies`). Null when the baseline sd is 0 or `data_available` is false. Computed for 2026 too, against the same baseline, for display only. |

**Invariants** (checked by `tests/test_export_contract.py`)
- `harmonized_low ≤ harmonized ≤ harmonized_high` wherever not null.
- `data_available == false` ⇒ `modis_raw`, `viirs_raw` (if beyond VIIRS data), `harmonized`,
  `harmonized_low`, `harmonized_high` and `anomaly_z` are null.
- `is_estimate == false` ⇒ `harmonized == viirs_raw`.
- (`cell_id`, `year`, `month`) is unique.

## Aggregating over areas (user-drawn polygons, provinces)
- **Counts and bands add up.** Sum `modis_raw`, `viirs_raw`, `harmonized`, `harmonized_low` and
  `harmonized_high` over the selected cells. The bands sum exactly, because every cell in a region uses the
  same calibration draw.
- **`anomaly_z` does not add up and must not be summed or averaged across cells.** Recompute it from the
  summed `harmonized` series:
  1. Sum `harmonized` over the cells for every month.
  2. For each calendar month, take the mean and sd of that sum over the baseline years
     (`meta.anomalies.baseline_years`, rows with `display_only = false`).
  3. z = (sum − mean) / sd. It is null when sd = 0 or the month has `data_available = false`.
- **Flags** propagate with OR (`is_estimate`, `has_gap`, `partial_month`, `display_only`, `low_confidence`)
  and with AND (`data_available`).
- **Hiding persistent cells.** Drop cells with `is_persistent` before summing. Then recompute
  `anomaly_z` from the new sum; region_monthly includes all cells.

## region_monthly.csv / region_monthly.json
- These are the same columns without `cell_id` and `is_persistent`, plus `n_cells` and `n_persistent_cells`.
- `region_monthly.json` holds the same rows as an array of objects; null is JSON `null`.
- **Counts** are sums over cells.
- **Bands** are the factor band applied to the region sum. That is the same calibration draw for every
  cell, so the band sums exactly.
- **`anomaly_z`** is computed on the region total against its own baseline. It is not the mean of the
  cell z values.

## cells.json

```json
{
  "contract_version": "0.2",
  "grid_size_deg": 0.05,
  "cell_id_rule": "row = floor((lat + 90) / 0.05), col = floor((lon + 180) / 0.05), cell_id = f'{row}_{col}'",
  "cells": [
    {"cell_id": "2470_4300", "row": 2470, "col": 4300,
     "lat_center": 33.525, "lon_center": 35.025,
     "bounds": [35.00, 33.50, 35.05, 33.55],
     "countries": ["Lebanon"], "primary_country": "Lebanon", "is_persistent": false}
  ]
}
```

- `bounds` is [west, south, east, north].
- `countries` lists every country with detections or territory in the cell. `primary_country` is the one
  with the largest share.
- Which cells are included: every cell whose centre is in the region's footprint (the region's countries,
  clipped to its bbox), plus any cell with at least one kept detection.
- `cell_id` is global, so the same cell has the same ID in every region's export.
- `cells.geojson` holds the same cells as Polygon features (WGS84, [lon, lat] order), with `cell_id` and the
  attributes above in `properties`.

## meta.json

```json
{
  "contract_version": "0.2",
  "region": "lebanon",
  "bbox": [35.00, 33.00, 36.70, 34.75],
  "countries": ["Lebanon"],
  "generated_at": "2026-11-20T10:00:00Z",
  "pipeline": {"version": "0.1.0", "config_hash": "sha256:…"},
  "units": "VIIRS-equivalent fire-days per 0.05° cell per month",
  "time": {
    "first_month": "2000-11", "last_month": "2026-12",
    "stats_last_year": 2025, "display_only_years": [2026],
    "splice_date": "2012-01-20", "terra_only_until": "2002-07-04"
  },
  "sources": {
    "MODIS_SP": {"satellites": ["Terra", "Aqua"], "first_date": "2000-11-01", "last_date": "2026-08-31"},
    "VIIRS_SNPP_SP": {"satellites": ["SNPP"], "first_date": "2012-01-20", "last_date": "2026-07-31"}
  },
  "calibration": {
    "strategy": "blend:eastmed_pool", "overlap_years": [2012, 2020], "blend_k": 20,
    "factors": [{"month": 1, "a": 0.0, "a_low": 0.0, "a_high": 0.0, "w_local": 0.0}],
    "terra_correction": [{"month": 1, "kT": 0.0, "kT_low": 0.0, "kT_high": 0.0}]
  },
  "validation": {
    "holdout": {"fit": [2012, 2016], "test": [2017, 2020]},
    "strategies": [{"strategy": "single", "wape": 0.0, "bias": 0.0}],
    "continuity_2012": {"ratio": 0.0, "band": [0.0, 0.0], "step_flagged": false}
  },
  "anomalies": {"baseline_years": [2001, 2025], "method": "z-score per cell and calendar month",
                "sensitivity": [{"baseline_years": [2012, 2025], "corr_z": 0.0, "mean_abs_dz": 0.0}]},
  "outages": [{"satellite": "SNPP", "start": "2022-07-27", "end": "2022-08-10"}],
  "caveats": [
    "Pre-2012 values are estimates converted from MODIS and must be labelled as such.",
    "Fire-days measure burning activity, not burned area.",
    "2026 is a partial year shown for display only."
  ]
}
```

The numbers above are placeholders. The keys are the contract.

### meta.json additions in 0.2
- `formats_status`: "pending confirmation from the frontend team".
- `n_cells`, `n_persistent_cells`.
- `calibration.factors[]`: `a, a_low, a_high, b, b_low, b_high, w_local` per month. `b` is the affine
  intercept, 0 for ratio strategies. `calibration.terra_strategy` gives the strategy used for kT.
- `low_confidence_rule`:
  - `min_modis_fire_days` and `max_zero_modis_share`;
  - `months`, the flagged calendar months;
  - `by_month`, the statistics behind the flags.
- `validation.continuity_2012`:
  - `band` includes year-to-year variation;
  - `band_factor_only` is the narrower factor-bootstrap band;
  - each has a `step_flagged` flag.

### Sizes (2026-11-12 run)

| region | cells | calendar rows | calendar.parquet | calendar.csv.gz | cells.geojson |
|---|---|---|---|---|---|
| lebanon | 429 | 134,706 | 0.1 MB | 0.4 MB | 0.15 MB |
| greece | 5,910 | 1,855,740 | 1.1 MB | 5.6 MB | 2.0 MB |
| eastmed | 15,872 | 4,983,808 | 3.4 MB | 15 MB | 5.3 MB |

For the browser, region_monthly.json (about 110 kB) and cells.geojson are the natural starting point.
Per-cell series can come from calendar.parquet (read with parquet-wasm or DuckDB-wasm) or
calendar.csv.gz.
