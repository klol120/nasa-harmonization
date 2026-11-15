# jordan: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `blend:southern_turkey`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.963 | [0.938, 1.003] | 46 | 60 | 0.767 |
| 2 | 0.928 | [0.878, 0.978] | 82 | 84 | 0.976 |
| 3 | 0.905 | [0.863, 0.948] | 78 | 102 | 0.765 |
| 4 | 0.927 | [0.826, 1.020] | 84 | 86 | 0.977 |
| 5 | 0.939 | [0.862, 1.058] | 194 | 199 | 0.975 |
| 6 | 0.972 | [0.947, 0.999] | 254 | 266 | 0.955 |
| 7 | 0.949 | [0.850, 1.042] | 182 | 200 | 0.910 |
| 8 | 0.996 | [0.957, 1.044] | 123 | 140 | 0.879 |
| 9 | 0.989 | [0.956, 1.017] | 141 | 177 | 0.797 |
| 10 | 0.973 | [0.946, 0.995] | 227 | 246 | 0.923 |
| 11 | 0.912 | [0.859, 0.959] | 147 | 184 | 0.799 |
| 12 | 0.953 | [0.922, 1.002] | 96 | 102 | 0.941 |

All months pooled (`single`): c = 0.896 [0.822, 0.977].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| blend:israel_palestine | 1e+09 | 0.323 | +21.7% | 0.286 | -19.3% |
| blend:southern_turkey | 1e+09 | 0.334 | +20.6% | 0.249 | -13.6% |
| blend:eastmed_pool | 1e+09 | 0.347 | +24.3% | 0.249 | -13.9% |
| single |  | 0.358 | +26.9% | 0.271 | -21.2% |
| blend:cyprus | 10 | 0.400 | +26.1% | 0.289 | -19.9% |
| blend:syria | 1e+09 | 0.416 | +33.5% | 0.263 | -16.1% |
| local |  | 0.419 | +28.8% | 0.291 | -19.9% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 240 | 250 | 239.5 | 1.042 | 0.998 | [0.736, 1.334] | no step | [0.968, 1.033] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 7 | 8 | 7.7 |
| 2026-02 | 17 | 11 | 10.2 |
| 2026-03 | 14 | 21 | 19.0 |
| 2026-04 | 13 | 16 | 14.8 |
| 2026-05 | 31 | 32 | 30.0 |
| 2026-06 | 46 | 43 | 41.8 |
| 2026-07 | 36 | 37 | 35.1 |
| 2026-08 | 19 | 27 | 26.9 |
| 2026-09 | 26 | 26 | 25.7 |
| 2026-10 | 29 | 29 | 28.2 |
| 2026-11 | 2 | 0 | 0.0 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 0.76, 2019: 0.98, 2020: 0.99, 2021: 0.96, 2022: 1.07, 2023: 1.15, 2024: 1.37, 2025: 1.15
