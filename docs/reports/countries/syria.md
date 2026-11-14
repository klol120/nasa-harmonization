# Syria (syria): add-country report

Added 2026-11-14 by `python -m firecal add-country Syria`. Config: `config.d/syria.yaml`. bbox [35.67, 32.26, 42.43, 37.37], 7512 cells.

**Quality grade B.** mean hold-out WAPE 0.252 <= 0.4, worst |bias| 11.0% <= 20%, no step at 2012.

| item | value |
|---|---|
| detections | 378,070 raw, 221,381 after cleaning |
| strategy | `local` (rich): 0/12 months thin (n < n_month 149): share 0.00 < n_country 0.72 |
| kT strategy | `local` |
| VIIRS/MODIS fire-days 2012–2020 | 3.461 |
| hold-out (forward / reverse) | WAPE 0.275, bias +11.0% / WAPE 0.229, bias -7.8% |
| step at 2012 | 1.187 (band [0.927, 1.464]) no step |
| NOAA-20 switch (`blend:southern_turkey`) | step 1.033, band [0.819, 1.165] no step |
| backend | loaded, listed by the API |
| runtime (s) | download 473.4, ingest_clean_grid 5.9, terra_calibrate_continuation 1.7, continuation_final 0.8, validate_splice_anomalies_export 99.8, backend 43.9, total 626.8 |

## Strategy rule by month

| month | n (MODIS fire-days 2012–2020) | thin | rule | a |
|---|---|---|---|---|
| Jan | 159 |  | rich_month | 4.535 |
| Feb | 294 |  | rich_month | 3.503 |
| Mar | 236 |  | rich_month | 4.606 |
| Apr | 183 |  | rich_month | 7.033 |
| May | 961 |  | rich_month | 3.648 |
| Jun | 2604 |  | rich_month | 2.838 |
| Jul | 2010 |  | rich_month | 3.093 |
| Aug | 1473 |  | rich_month | 3.386 |
| Sep | 1620 |  | rich_month | 3.591 |
| Oct | 1220 |  | rich_month | 4.045 |
| Nov | 567 |  | rich_month | 3.617 |
| Dec | 166 |  | rich_month | 4.494 |
