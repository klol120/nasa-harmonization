# Cyprus (cyprus): add-country report

Added 2026-11-14 by `python -m firecal add-country Cyprus`. Config: `config.d/cyprus.yaml`. bbox [32.22, 34.58, 34.15, 35.24], 247 cells.

**Quality grade D.** mean hold-out WAPE 0.604, worst |bias| 16.3%: beyond every grade.

| item | value |
|---|---|
| detections | 10,604 raw, 6,474 after cleaning |
| strategy | `affine_shape_single_level_pool_ex_cyprus` (thin): 12/12 months thin (n < n_month 149): share 1.00 >= n_country 0.72 |
| kT strategy | `single` |
| VIIRS/MODIS fire-days 2012–2020 | 3.98 |
| hold-out (forward / reverse) | WAPE 0.559, bias -14.0% / WAPE 0.648, bias +16.3% |
| step at 2012 | 0.971 (band [0.74, 1.277]) no step |
| NOAA-20 switch (`single`) | step 1.222, band [0.938, 1.577] no step |
| backend | loaded, listed by the API |
| runtime (s) | download 405.0, ingest_clean_grid 1.5, terra_calibrate_continuation 1.7, continuation_final 0.7, validate_splice_anomalies_export 16.9, backend 3.4, total 430.3 |

## Strategy rule by month

| month | n (MODIS fire-days 2012–2020) | thin | rule | a |
|---|---|---|---|---|
| Jan | 3 | thin | thin_month | 3.98 |
| Feb | 4 | thin | thin_month | 3.98 |
| Mar | 6 | thin | thin_month | 3.98 |
| Apr | 6 | thin | thin_month | 3.98 |
| May | 10 | thin | thin_month | 3.98 |
| Jun | 35 | thin | thin_month | 3.98 |
| Jul | 26 | thin | thin_month | 3.98 |
| Aug | 34 | thin | thin_month | 3.98 |
| Sep | 25 | thin | thin_month | 3.98 |
| Oct | 35 | thin | thin_month | 3.98 |
| Nov | 42 | thin | thin_month | 3.98 |
| Dec | 25 | thin | thin_month | 3.98 |
