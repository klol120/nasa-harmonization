# eastmed: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `local`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.983 | [0.964, 1.023] | 4285 | 4361 | 0.983 |
| 2 | 0.932 | [0.884, 0.995] | 2057 | 2207 | 0.932 |
| 3 | 0.947 | [0.886, 1.020] | 1728 | 1825 | 0.947 |
| 4 | 0.922 | [0.856, 1.011] | 1579 | 1712 | 0.922 |
| 5 | 0.986 | [0.919, 1.050] | 4436 | 4499 | 0.986 |
| 6 | 0.985 | [0.951, 1.023] | 14197 | 14408 | 0.985 |
| 7 | 0.956 | [0.856, 1.044] | 9598 | 10038 | 0.956 |
| 8 | 1.014 | [0.969, 1.050] | 9787 | 9650 | 1.014 |
| 9 | 0.993 | [0.958, 1.019] | 14713 | 14816 | 0.993 |
| 10 | 0.976 | [0.960, 0.989] | 14874 | 15239 | 0.976 |
| 11 | 0.902 | [0.857, 0.941] | 10819 | 11994 | 0.902 |
| 12 | 0.952 | [0.922, 1.002] | 6856 | 7198 | 0.952 |

All months pooled (`single`): c = 0.969 [0.941, 0.996].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| local |  | 0.084 | +6.7% | 0.081 | -6.7% |
| single |  | 0.086 | +7.0% | 0.077 | -6.5% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 8748 | 9405 | 9225.1 | 1.075 | 1.055 | [0.991, 1.157] | no step | [1.018, 1.086] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 132 | 160 | 157.2 |
| 2026-02 | 295 | 310 | 288.9 |
| 2026-03 | 167 | 244 | 231.0 |
| 2026-04 | 88 | 130 | 119.9 |
| 2026-05 | 159 | 196 | 193.3 |
| 2026-06 | 1255 | 1270 | 1251.4 |
| 2026-07 | 1248 | 1539 | 1471.5 |
| 2026-08 | 1188 | 1234 | 1251.5 |
| 2026-09 | 2452 | 2556 | 2538.2 |
| 2026-10 | 1743 | 1744 | 1702.2 |
| 2026-11 | 21 | 22 | 19.8 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 0.97, 2019: 0.95, 2020: 0.97, 2021: 1.01, 2022: 1.00, 2023: 1.00, 2024: 1.09, 2025: 1.02
