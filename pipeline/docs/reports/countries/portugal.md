# Portugal (portugal): add-country report

Added 2026-11-14 by `python -m firecal add-country Portugal`. Config: `config.d/portugal.yaml`. bbox [-9.55, 36.94, -6.16, 42.2], 3811 cells.

**Quality grade B.** mean hold-out WAPE 0.212 <= 0.4, worst |bias| 12.3% <= 20%, no step at 2012.

| item | value |
|---|---|
| detections | 245,126 raw, 226,100 after cleaning |
| strategy | `local` (rich): 0/12 months thin (n < n_month 149): share 0.00 < n_country 0.72 |
| kT strategy | `local` |
| VIIRS/MODIS fire-days 2012–2020 | 1.701 |
| hold-out (forward / reverse) | WAPE 0.231, bias +12.3% / WAPE 0.192, bias -6.1% |
| step at 2012 | 1.098 (band [0.943, 1.242]) no step |
| NOAA-20 switch (`single`) | step 0.996, band [0.960, 1.055] no step |
| backend | loaded, listed by the API |
| runtime (s) | download 545.4, ingest_clean_grid 4.1, terra_calibrate_continuation 2.2, continuation_final 1.0, validate_splice_anomalies_export 57.8, backend 21.4, total 632.9 |

## Strategy rule by month

| month | n (MODIS fire-days 2012–2020) | thin | rule | a |
|---|---|---|---|---|
| Jan | 261 |  | rich_month | 3.08 |
| Feb | 745 |  | rich_month | 2.114 |
| Mar | 1226 |  | rich_month | 1.803 |
| Apr | 534 |  | rich_month | 2.423 |
| May | 266 |  | rich_month | 2.782 |
| Jun | 315 |  | rich_month | 1.917 |
| Jul | 822 |  | rich_month | 1.483 |
| Aug | 2676 |  | rich_month | 1.241 |
| Sep | 1481 |  | rich_month | 1.447 |
| Oct | 1195 |  | rich_month | 1.541 |
| Nov | 266 |  | rich_month | 2.436 |
| Dec | 200 |  | rich_month | 2.935 |
