# Export preview (sanity check only, not the frontend)

```
.venv/bin/python -m http.server 8000        # from the repo root
open http://localhost:8000/tools/preview/?region=lebanon
node tools/preview/check.mjs                # data checks of the helpers against data/export
```

What it shows:
- A year × month heatmap from `region_monthly.json`, with a MODIS / VIIRS / Harmonized toggle (sqrt colour
  scale, grey for no data, hatching for `low_confidence`). Tooltips show the band, raw counts, z and flags.
- A MapLibre map of `cells.geojson`, coloured by the month clicked in the heatmap from
  `cells_series/{year}.json` (contract 0.4, all regions). Persistent cells have a red outline. A banner
  names the month and says "MODELLED ESTIMATE (not detections)" when `is_estimate` is true.

**Status:** the code passes `node --check`, and `check.mjs` passes on the real exports. The page has not
been opened in a browser yet (built unattended). The basemap is MapLibre's public demo style, so it needs
internet access.

## What made the 0.3 exports awkward (items 1, 3, 4, 5 and 6 are fixed in contract 0.4)
1. **No small per-cell format.** Per-cell values exist only in `calendar.parquet` (needs parquet-wasm or
   DuckDB-wasm) or `calendar.csv.gz`. The CSV has to be downloaded whole and gunzipped in the page
   (5.6 MB Greece, 15 MB EastMed). A per-year or per-month JSON (cell_id → value) would suit a map much
   better.
2. **The gzip handling depends on the server.** `python -m http.server` sends `.csv.gz` as
   application/gzip, so the page decompresses it with DecompressionStream. A server that adds
   `Content-Encoding: gzip` would make the browser decompress it first and this code would fail.
3. **MODIS and VIIRS/harmonized are in different units.** MODIS raw fire-days are about 3–6× smaller.
   One shared colour scale across the toggle would mislead, so each variable gets its own scale. The
   contract could say this explicitly.
4. **Geometry is stored twice.** `cells.geojson` (5.3 MB for EastMed) repeats what `cells.json` already
   holds (bounds), and both could be rebuilt from `cell_id` and the grid rule. One of the two is enough.
5. **No month key.** `year` and `month` are separate columns, so every lookup builds a `"y-m"` key. A
   `"YYYY-MM"` field would help.
6. **Region-wide flags repeat on every cell row.** `low_confidence`, `has_gap`, `data_available`,
   `display_only` and `partial_month` are the same for all cells in a month, yet they are repeated on
   every calendar row (most of the CSV's size). They could live in region_monthly only.
7. **Nothing to stop summing z.** Nothing in the files prevents summing `anomaly_z` across cells (the
   contract says not to). A map legend needs the region baseline, which only meta.json describes.
