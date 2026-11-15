# syria: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `blend:southern_turkey`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.963 | [0.938, 1.003] | 543 | 482 | 1.127 |
| 2 | 0.928 | [0.878, 0.978] | 476 | 512 | 0.930 |
| 3 | 0.905 | [0.863, 0.948] | 532 | 511 | 1.041 |
| 4 | 0.927 | [0.826, 1.020] | 546 | 547 | 0.998 |
| 5 | 0.939 | [0.862, 1.058] | 2225 | 2154 | 1.033 |
| 6 | 0.972 | [0.947, 0.999] | 5686 | 5582 | 1.019 |
| 7 | 0.949 | [0.850, 1.042] | 4035 | 4109 | 0.982 |
| 8 | 0.996 | [0.957, 1.044] | 3367 | 3178 | 1.059 |
| 9 | 0.989 | [0.956, 1.017] | 4964 | 4971 | 0.999 |
| 10 | 0.973 | [0.946, 0.995] | 4905 | 4971 | 0.987 |
| 11 | 0.912 | [0.859, 0.959] | 1717 | 1951 | 0.880 |
| 12 | 0.953 | [0.922, 1.002] | 394 | 428 | 0.921 |

All months pooled (`single`): c = 1.000 [0.946, 1.038].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| single |  | 0.151 | +11.9% | 0.128 | -10.7% |
| blend:southern_turkey | 100 | 0.152 | +12.4% | 0.112 | -9.2% |
| blend:eastmed_pool_ex_syria | 100 | 0.152 | +12.4% | 0.114 | -9.5% |
| blend:cyprus | 50 | 0.154 | +12.7% | 0.125 | -11.0% |
| blend:israel_palestine | 100 | 0.155 | +12.8% | 0.118 | -10.3% |
| local |  | 0.166 | +14.2% | 0.121 | -10.5% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 3534 | 3744 | 3649.5 | 1.059 | 1.033 | [0.819, 1.165] | no step | [0.997, 1.066] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 24 | 24 | 23.1 |
| 2026-02 | 68 | 66 | 61.2 |
| 2026-03 | 33 | 57 | 51.6 |
| 2026-04 | 9 | 15 | 13.9 |
| 2026-05 | 44 | 50 | 46.9 |
| 2026-06 | 325 | 299 | 290.6 |
| 2026-07 | 594 | 711 | 674.5 |
| 2026-08 | 662 | 707 | 704.4 |
| 2026-09 | 1052 | 1101 | 1088.9 |
| 2026-10 | 714 | 707 | 687.9 |
| 2026-11 | 9 | 7 | 6.4 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 0.78, 2019: 0.93, 2020: 0.94, 2021: 1.07, 2022: 1.04, 2023: 0.97, 2024: 1.08, 2025: 1.07
