# Data contract: burning-activity calendar export

Version **0.4** (draft, 2026-11-12). Producer: `firecal export`. Consumer: the frontend team (browser app).
The formats are still pending confirmation from the frontend team.

**Changes from 0.3** (breaking):
- **New compact per-cell file:** `cells_series/{year}.json`.
- **Region-wide flags moved to `region_monthly`:** `is_estimate`, `has_gap`, `data_available`,
  `partial_month`, `display_only` and `low_confidence` are no longer repeated on calendar rows.
- **`is_persistent` is now only in `cells.geojson`.**
- **New `ym` field** ("YYYY-MM") in the calendar, `region_monthly` and the series files.
- **`cells.json` dropped**; use `cells.geojson`.
- **New `meta.files`** listing every file with its size in bytes.

## Files (`data/export/{region}/`, region = lebanon | greece | eastmed)

| file | content | use |
|---|---|---|
| `region_monthly.json` / `.csv` | one row per month: region totals **and all region-wide flags** | calendar heatmap, region charts, flags for every map view |
| `cells.geojson` | one Polygon per 0.05° cell, cell attributes in `properties` | map geometry |
| `cells_series/{year}.json` | compact per-cell monthly values for one year | map colouring |
| `calendar.parquet` / `calendar.csv.gz` | one row per cell per month, all per-cell values incl. bands and z | analysis, area aggregation, download |
| `meta.json` | units, dates, calibration, validation, rules, file sizes | legends, labels, about box |

Compatibility: fields may be added in a minor version, so ignore unknown fields. A rename, removal or type
change bumps the version (`contract_version` in meta.json and the series files).

## Units and what the numbers are
- **Fire-day:** one 0.05° cell with at least one active-fire detection on one UTC day. A cell-month value
  lies between 0 and the number of days in the month. Fire-days measure burning activity, not burned area.
- **`harmonized`** is in **VIIRS-equivalent fire-days**. It is observed VIIRS from 2012-01-20 onward;
  before that it is a model estimate converted from MODIS.
- **`viirs_raw`** is in VIIRS fire-days (null before 2012-01).
- **`modis_raw` is in MODIS fire-days, a different and much smaller unit.** MODIS sees roughly 3–6× fewer
  fire-days than VIIRS for the same activity (about 3× in Greece, about 6× in Lebanon). It is not
  comparable with `harmonized` or `viirs_raw`. **Give MODIS its own colour scale** and never share a
  legend between MODIS and the VIIRS-unit variables.
- **Pre-2012 cell values are modelled, not detections.** This matters most for Lebanon. A pre-2012 cell
  value is a region-level conversion of MODIS spread over cells, and with Lebanon's default strategy
  (`affine_shape_single_level_pool`) part of it is an intercept spread over cells by their 2012–2020
  VIIRS share. So a cell can show activity in a month in which no satellite detected anything there.
  - **Any map view of a month with `is_estimate = true` must say so**, e.g. "Modelled estimate (not
    detections)".
  - Every pre-2012 Lebanon month is also `low_confidence = true`. Show those with extra caution
    (hatching, a muted palette).
  - Greece and EastMed estimates come from a per-month ratio applied to each cell's own MODIS count, so
    those cells are non-zero only where MODIS detected fire. They are still estimates and must be
    labelled the same way.

## region_monthly (the region-month table)
One row per month from `meta.time.first_month` to `meta.time.last_month`; every month has a row.

| field | type | null? | meaning |
|---|---|---|---|
| `ym` | string | no | "YYYY-MM" |
| `year`, `month` | int | no | |
| `modis_raw`, `viirs_raw` | int | yes | region sums (MODIS units / VIIRS units); null when that sensor has no data |
| `harmonized`, `harmonized_low`, `harmonized_high` | float | yes | region sum and 90% band. Null iff `data_available` is false |
| `anomaly_z` | float | yes | z of the region total against its own baseline (`meta.anomalies.baseline_years`) |
| `is_estimate` | bool | no | the month is (wholly or partly) estimated from MODIS: all months ≤ 2011-12 and 2012-01 |
| `has_gap` | bool | no | at least one satellite-outage day for a sensor feeding the month |
| `data_available` | bool | no | false when the feeding sensor has no data (e.g. 2026 months after the last date). Show "no data", never 0 |
| `partial_month` | bool | no | data covers only part of the month |
| `display_only` | bool | no | partial year (2026): shown, but excluded from calibration and baselines |
| `low_confidence` | bool | no | estimated month whose calendar month fails `meta.low_confidence_rule` |
| `n_cells`, `n_persistent_cells` | int | no | cells in the region / cells flagged `is_persistent` |

These flags apply to **every cell** of the region in that month; the per-cell files do not repeat them.

## cells.geojson
A FeatureCollection with one Polygon per cell (WGS84, [lon, lat]). Properties:
- `cell_id`, `row`, `col`, `lat_center`, `lon_center`;
- `countries` (list), `primary_country`;
- `is_persistent`: the cell contains a persistent industrial or waste-burning source. These cells are
  excluded from calibration fitting but kept in the data, so the UI may show or hide them.

`cell_id` = `f"{row}_{col}"` with row = floor((lat + 90) / 0.05) and col = floor((lon + 180) / 0.05). It
is global, so the same cell has the same ID in every region.

## cells_series/{year}.json (compact per-cell file)

```json
{"contract_version": "0.4", "year": 2007, "ym": ["2007-01", "...", "2007-12"],
 "fields": {"h": "harmonized", "m": "modis_raw", "v": "viirs_raw"},
 "omitted_cells": "no fire-days this year: 0 where data_available, else null",
 "cells": {"2461_4303": {"h": [0, 0, ..., 0.17, 0, 0, 0], "m": [0, ...], "v": [null, ...]}}}
```

- The arrays are aligned with `ym`. `h` is rounded to 0.01; `m` and `v` are integers; `null` means no
  data.
- **Cells absent from `cells` had no fire-days that year.** Read them as 0 in months where
  `region_monthly.data_available` is true, and as null otherwise.
- Bands and z are not in the series files; take them from `calendar.parquet` when needed.
- The 2026 file covers the months that exist (to 2026-12, data to 2026-07 for VIIRS).

## calendar (one row per cell × month)

| field | type | null? | meaning |
|---|---|---|---|
| `cell_id` | string | no | |
| `ym` | string | no | "YYYY-MM" |
| `year`, `month` | int16, int8 | no | |
| `modis_raw` | Int16 | yes | MODIS (Terra ∪ Aqua) fire-days; **MODIS units** |
| `viirs_raw` | Int16 | yes | VIIRS S-NPP fire-days; null before 2012-01; January 2012 counts days from the 20th |
| `harmonized`, `harmonized_low`, `harmonized_high` | float32 | yes | VIIRS-equivalent value and 90% band. Bands equal the value for observed months |
| `anomaly_z` | float32 | yes | cell z against the cell's baseline for that calendar month; null when baseline sd = 0 or no data |

Invariants (checked by `tests/test_export_contract.py`):
- `harmonized_low ≤ harmonized ≤ harmonized_high`;
- `harmonized` is null iff the month's `data_available` is false;
- for observed months `harmonized == viirs_raw`;
- (`cell_id`, `ym`) is unique;
- the series files equal the calendar values.

## Aggregating over areas (user-drawn polygons, provinces)
- **Counts and bands add up.** Sum `harmonized`, `harmonized_low`, `harmonized_high`, `modis_raw` and
  `viirs_raw` over the cells. Every cell of a region uses the same calibration draw, so the bands sum
  exactly.
- **`anomaly_z` must not be summed or averaged across cells.** Recompute it from the summed series:
  1. For each calendar month, take the mean and sd of the summed `harmonized` over
     `meta.anomalies.baseline_years`, using months with `display_only = false`. **The baseline is per
     region:** Lebanon 2012–2025, Greece and EastMed 2001–2025.
  2. z = (sum − mean) / sd. It is null when sd = 0 or `data_available` is false.
- **Flags** come from `region_monthly` and are identical for every cell of the region.
- **Hiding persistent cells:** drop cells with `is_persistent`, then recompute sums and z.

## meta.json
- **Identity:** `contract_version`, `region`, `bbox`, `countries`, `generated_at`, `pipeline`
  (version, config hash), `formats_status`, `units`, `n_cells`, `n_persistent_cells`.
- **`files`:** `{path: bytes}` for every exported file.
- **`time`:** `first_month`, `last_month`, `stats_last_year`, `display_only_years`, `splice_date`
  (2012-01-20) and `terra_only_until` (2002-07-04). `sources`: first and last date per product.
- **`calibration`:**
  - `strategy`, `overlap_years`, `exclude_persistent_from_fit`;
  - `factors[]` (`a, a_low, a_high, b, b_low, b_high, w_local` per month), plus `terra_strategy` and
    `terra_correction[]`;
  - `composite`, when the strategy is a composite: `shape` and `level` with their factors. In that case
    `factors[]` are the level model's, and bands carry the level model's uncertainty only.
- **`low_confidence_rule`:** the region's thresholds (`min_modis_fire_days`, `max_zero_modis_share`),
  `months` (the flagged calendar months) and `by_month` (the statistics behind them).
- **`validation`:** the hold-out table per strategy, and `continuity_2012` with `step_index`, `band`
  (with year-to-year spread), `band_factor_only` and the flags.
- **`anomalies`:** `baseline_years`, `baseline_source` and `sensitivity` (alternative baseline: correlation
  and mean |Δz|). `outages`: confirmed outage runs. `caveats`: text for the about box.

## Sizes (2026-11-12 run)

| region | cells | cells.geojson | cells_series (largest year / all) | region_monthly.json | calendar.parquet | calendar.csv.gz |
|---|---|---|---|---|---|---|
| lebanon | 429 | 0.15 MB | 0.06 / 0.93 MB | 0.11 MB | 0.29 MB | 0.67 MB |
| greece | 5,910 | 1.99 MB | 0.20 / 3.60 MB | 0.11 MB | 1.27 MB | 6.40 MB |
| eastmed | 15,872 | 5.32 MB | 0.72 / 10.4 MB | 0.11 MB | 3.88 MB | 17.2 MB |

A browser map needs `region_monthly.json`, `cells.geojson` and one `cells_series/{year}.json` at a time:
under 0.5 MB for Lebanon and about 6 MB for EastMed.

## Shared files (in git)
Committed for sharing, with a limit of 5 MB (5,000,000 bytes):
- **`lebanon/`:** all files, including `cells_series/`.
- **All regions:** `region_monthly.json` and `cells_series/` (each year file is 0.72 MB or less).
- **`greece/cells.geojson`.**

**Too large for git, share separately:**

| file | size |
|---|---|
| `eastmed/cells.geojson` | 5.3 MB |
| `greece/calendar.csv.gz` | 6.4 MB |
| `eastmed/calendar.csv.gz` | 17.2 MB |

Everything else regenerates with `.venv/bin/python -m firecal all --region <region>`.
