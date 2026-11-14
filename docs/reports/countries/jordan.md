# Jordan (jordan): add-country report

Added 2026-11-14 by `python -m firecal add-country Jordan`. Config: `config.d/jordan.yaml`. bbox [34.9, 29.14, 39.34, 33.42], 3399 cells.

**Quality grade C.** mean hold-out WAPE 0.492 <= 0.6, worst |bias| 18.9% <= 35%, no step at 2012.

| item | value |
|---|---|
| detections | 17,611 raw, 9,920 after cleaning |
| strategy | `affine_shape_single_level_pool` (thin): 12/12 months thin (n < n_month 149): share 1.00 >= n_country 0.72 |
| kT strategy | `single` |
| VIIRS/MODIS fire-days 2012–2020 | 6.138 |
| hold-out (forward / reverse) | WAPE 0.466, bias +18.9% / WAPE 0.518, bias -15.9% |
| step at 2012 | 1.733 (band [0.977, 2.879]) no step |
| NOAA-20 switch (`blend:southern_turkey`) | step 0.998, band [0.736, 1.334] no step |
| backend | loaded, listed by the API |
| runtime (s) | download 521.8, ingest_clean_grid 1.7, terra_calibrate_continuation 2.0, continuation_final 0.9, validate_splice_anomalies_export 54.8, backend 18.5, total 600.8 |

## Strategy rule by month

| month | n (MODIS fire-days 2012–2020) | thin | rule | a |
|---|---|---|---|---|
| Jan | 33 | thin | thin_month | 6.138 |
| Feb | 29 | thin | thin_month | 6.138 |
| Mar | 2 | thin | thin_month | 6.138 |
| Apr | 15 | thin | thin_month | 6.138 |
| May | 27 | thin | thin_month | 6.138 |
| Jun | 31 | thin | thin_month | 6.138 |
| Jul | 21 | thin | thin_month | 6.138 |
| Aug | 19 | thin | thin_month | 6.138 |
| Sep | 15 | thin | thin_month | 6.138 |
| Oct | 17 | thin | thin_month | 6.138 |
| Nov | 29 | thin | thin_month | 6.138 |
| Dec | 52 | thin | thin_month | 6.138 |
