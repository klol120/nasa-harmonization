# While you were away (2026-11-12, second session)

## Most important first
1. **Lebanon's default is now `affine_shape_single_level`.** It passed all three adoption checks:
   - **continuity:** step 1.025, inside the band;
   - **bias:** equal to single's on both folds (−4.7% forward, +4.9% reverse);
   - **WAPE:** 0.338 vs 0.547 forward and 0.417 vs 0.532 reverse, i.e. 0.21 and 0.11 lower.

   It is single's annual level with the monthly shape of the best affine model (`affine_blend:cyprus`).
   To revert: `calibration.strategy.lebanon: single`.
2. **Everything is merged into `main`**, and all 81 tests pass there. The two branches from tonight
   (`autonomous-phase4-5`, `autonomous-night2`) are merged. Nothing is pushed.
3. **Every pre-2012 Lebanon month is now `low_confidence`** (80% threshold). Greece and EastMed keep 95%,
   because 80% would have flagged 10 of 12 calendar months in each.
4. **Exports are regenerated for all three regions**, data contract 0.3. Shareable files are committed;
   three large files are not (see below).
5. **The preview page `tools/preview/` is built** and its data checks pass, but it has **not been opened
   in a browser yet**.

## Decisions taken on your behalf
- **low_confidence (step 2).** Before → after, by calendar month:

  | region | 95% | 80% |
  |---|---|---|
  | lebanon | 1–6, 12 | **1–12** (all pre-2012 months confirmed flagged) |
  | greece | 5 | 1–6, 9–12 (10 months) |
  | eastmed | none | 1–5, 7, 9–12 (10 months) |

  Greece and EastMed flagged more than 3 months, so 80% is Lebanon-only via
  `low_confidence.by_region.lebanon`.
- **Anomaly baselines (step 3)** via `anomalies.by_region`: Lebanon 2012–2025, with sensitivity against
  2001–2025; Greece and EastMed 2001–2025. Recorded in `meta.json` (`anomalies.baseline_years`,
  `baseline_source`).
- **"Best affine model"** means the best-ranked affine strategy under the same ranking rule:
  `affine_blend:cyprus` (k = 0, essentially `affine_local`). It is fixed in
  `calibration.composites` for reproducibility.
- **Adoption-rule reading.** I required the WAPE gain of 0.10 on both folds, and "no worse" bias as
  |bias| ≤ single's |bias| on each fold. The composite's bias equals single's by construction, because it
  keeps single's annual totals.
- **Composite bands** carry the level model's (single's) uncertainty only. The shape's uncertainty is not
  propagated, and this is noted in `meta.calibration.composite.bands`.
- **5 MB limit** taken as 5,000,000 bytes. Shared files are whitelisted in `.gitignore`, so a rerun
  keeps the same set tracked.

## Lebanon comparison (persistence-excluded fitting; full table in `lebanon_experiment.md`)

| rank | strategy | step | new band | fwd bias | fwd WAPE | rev bias | rev WAPE |
|---|---|---|---|---|---|---|---|
| **1** | **affine_shape_single_level** (default) | 1.025 | ok | −4.7% | **0.338** | +4.9% | **0.417** |
| 2 | single (previous default) | 1.025 | ok | −4.7% | 0.547 | +4.9% | 0.532 |
| 3 | local | 1.033 | ok | +2.0% | 0.525 | +19.8% | 0.622 |
| 4 | affine_blend:cyprus | 1.138 | ok | +3.2% | 0.283 | −1.0% | 0.373 |
| 6 | blend:israel_palestine | 1.126 | ok | −12.7% | 0.414 | +6.3% | 0.498 |
| 9 | affine_local | 1.138 | flag | +3.2% | 0.283 | −3.3% | 0.298 |
| 19 | blend:eastmed_pool (original) | 1.284 | flag | −27.5% | 0.437 | −3.6% | 0.445 |

The yearly bias pattern is the same as single's (2019 −25%, 2020 +30%), since the annual totals are equal.

## Files committed for sharing (`data/export/`)
- **Committed:**
  - `lebanon/`, all 7 files;
  - `region_monthly.json` for all three regions;
  - `cells.geojson` for Lebanon and Greece.
- **Too large, share separately** (listed in `docs/data_contract.md`):

  | file | size |
  |---|---|
  | `eastmed/cells.geojson` | 5.3 MB |
  | `greece/calendar.csv.gz` | 5.6 MB |
  | `eastmed/calendar.csv.gz` | 15.2 MB |

- Other Greece/EastMed files are not committed because they weren't in the requested set. Regenerate
  with `python -m firecal all`.

## Fixed along the way
- **Isolated test configs.** Config overrides could not replace a section: `donors: {}` merged and did
  nothing, so the synthetic tests silently kept the real regions and donors. I added a `"key!"` replace
  marker and the tests now use it.
- **Unconfigured donor regions.** A donor group whose region isn't configured is now unavailable instead
  of crashing.
- No test was loosened or deleted. One new test of mine had an off-by-one year range, which I corrected.

## Preview page (`tools/preview/`)
- **What it does:** a heatmap from `region_monthly.json` with a MODIS/VIIRS/Harmonized toggle and hatched
  low_confidence months, and a MapLibre map of cells (Lebanon cells coloured per clicked month).
- **Checked:** `node --check` and `check.mjs` pass on the real exports, and the files are served
  correctly. Not checked: opening the page in a browser.
- **What made the exports awkward**, detailed in its README:
  - no small per-cell format;
  - gzip CSV handling depends on the server;
  - MODIS vs VIIRS units need separate colour scales;
  - geometry is stored twice (cells.json and cells.geojson);
  - no `YYYY-MM` key;
  - region-wide flags are repeated on every cell row.

## Review first
1. The new Lebanon default. Its winter estimates are non-zero even where MODIS saw nothing, because of
   the affine intercept spread over cells by their VIIRS share.
2. Open the preview: run `.venv/bin/python -m http.server 8000`, then open
   `http://localhost:8000/tools/preview/`.
3. The export-format suggestions in `tools/preview/README.md`, before the frontend team builds on 0.3.
4. Still pending from before: the outage suspects list, and the missing Northern Cyprus coverage.
