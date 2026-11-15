# Turkey (turkey): add-country report

Added 2026-11-14 by `python -m firecal add-country Turkey`. Config: `config.d/turkey.yaml`. bbox [25.98, 35.77, 44.86, 42.15], 32894 cells.

**Quality grade B.** mean hold-out WAPE 0.150 <= 0.4, worst |bias| 10.4% <= 20%, no step at 2012.

| item | value |
|---|---|
| detections | 1,255,497 raw, 879,340 after cleaning |
| strategy | `local` (rich): 0/12 months thin (n < n_month 149): share 0.00 < n_country 0.72 |
| kT strategy | `local` |
| VIIRS/MODIS fire-days 2012–2020 | 2.463 |
| hold-out (forward / reverse) | WAPE 0.143, bias -7.4% / WAPE 0.157, bias +10.4% |
| step at 2012 | 0.962 (band [0.884, 1.039]) no step |
| NOAA-20 switch (`single`) | step 1.039, band [0.998, 1.127] no step |
| backend | not loaded, not listed — teammate repo is on 'monorepo', expected 'contract-0.5'; not loaded |
| runtime (s) | download 485.2, ingest_clean_grid 30.5, terra_calibrate_continuation 2.2, continuation_final 1.3, validate_splice_anomalies_export 423.1, total 943.3 |

## Strategy rule by month

| month | n (MODIS fire-days 2012–2020) | thin | rule | a |
|---|---|---|---|---|
| Jan | 1009 |  | rich_month | 2.834 |
| Feb | 1047 |  | rich_month | 2.967 |
| Mar | 1479 |  | rich_month | 3.023 |
| Apr | 1311 |  | rich_month | 2.969 |
| May | 1445 |  | rich_month | 1.451 |
| Jun | 9761 |  | rich_month | 1.3 |
| Jul | 5564 |  | rich_month | 2.23 |
| Aug | 7379 |  | rich_month | 2.778 |
| Sep | 10423 |  | rich_month | 3.031 |
| Oct | 9342 |  | rich_month | 2.989 |
| Nov | 7939 |  | rich_month | 2.273 |
| Dec | 2358 |  | rich_month | 2.493 |
