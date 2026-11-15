# lebanon: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `single`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.928 | [0.882, 0.966] | 56 | 53 | 1.057 |
| 2 | 0.928 | [0.882, 0.966] | 50 | 45 | 1.111 |
| 3 | 0.928 | [0.882, 0.966] | 84 | 80 | 1.050 |
| 4 | 0.928 | [0.882, 0.966] | 100 | 109 | 0.917 |
| 5 | 0.928 | [0.882, 0.966] | 155 | 155 | 1.000 |
| 6 | 0.928 | [0.882, 0.966] | 290 | 320 | 0.906 |
| 7 | 0.928 | [0.882, 0.966] | 411 | 431 | 0.954 |
| 8 | 0.928 | [0.882, 0.966] | 397 | 394 | 1.008 |
| 9 | 0.928 | [0.882, 0.966] | 498 | 539 | 0.924 |
| 10 | 0.928 | [0.882, 0.966] | 566 | 624 | 0.907 |
| 11 | 0.928 | [0.882, 0.966] | 206 | 283 | 0.728 |
| 12 | 0.928 | [0.882, 0.966] | 67 | 71 | 0.944 |

All months pooled (`single`): c = 0.928 [0.882, 0.966].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| single |  | 0.176 | +0.4% | 0.205 | -0.4% |
| blend:cyprus | 50 | 0.187 | -0.1% | 0.215 | -1.9% |
| local |  | 0.189 | +1.4% | 0.213 | -0.6% |
| blend:southern_turkey | 1e+09 | 0.201 | +5.2% | 0.210 | -0.6% |
| blend:eastmed_pool | 1e+09 | 0.206 | +7.7% | 0.211 | -0.9% |
| blend:israel_palestine | 1e+09 | 0.206 | +5.8% | 0.214 | -0.8% |
| blend:syria | 1e+09 | 0.221 | +12.7% | 0.217 | -0.8% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 312 | 312 | 289.5 | 1.000 | 0.928 | [0.814, 1.085] | no step | [0.882, 0.966] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 6 | 3 | 2.8 |
| 2026-02 | 1 | 1 | 0.9 |
| 2026-03 | 4 | 4 | 3.7 |
| 2026-04 | 4 | 6 | 5.6 |
| 2026-05 | 10 | 10 | 9.3 |
| 2026-06 | 45 | 35 | 32.5 |
| 2026-07 | 69 | 80 | 74.2 |
| 2026-08 | 95 | 98 | 90.9 |
| 2026-09 | 54 | 54 | 50.1 |
| 2026-10 | 24 | 21 | 19.5 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 1.17, 2019: 0.90, 2020: 1.12, 2021: 0.92, 2022: 0.98, 2023: 1.04, 2024: 0.98, 2025: 1.02
