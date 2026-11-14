# portugal: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `single`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.965 | [0.951, 0.977] | 754 | 764 | 0.987 |
| 2 | 0.965 | [0.951, 0.977] | 771 | 815 | 0.946 |
| 3 | 0.965 | [0.951, 0.977] | 894 | 936 | 0.955 |
| 4 | 0.965 | [0.951, 0.977] | 635 | 617 | 1.029 |
| 5 | 0.965 | [0.951, 0.977] | 469 | 465 | 1.009 |
| 6 | 0.965 | [0.951, 0.977] | 215 | 222 | 0.968 |
| 7 | 0.965 | [0.951, 0.977] | 774 | 843 | 0.918 |
| 8 | 0.965 | [0.951, 0.977] | 1510 | 1546 | 0.977 |
| 9 | 0.965 | [0.951, 0.977] | 1231 | 1237 | 0.995 |
| 10 | 0.965 | [0.951, 0.977] | 675 | 681 | 0.991 |
| 11 | 0.965 | [0.951, 0.977] | 374 | 430 | 0.870 |
| 12 | 0.965 | [0.951, 0.977] | 230 | 288 | 0.799 |

All months pooled (`single`): c = 0.965 [0.951, 0.977].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| single |  | 0.082 | -2.5% | 0.089 | +2.5% |
| blend:eastmed_pool | 50 | 0.092 | -2.5% | 0.096 | +1.7% |
| blend:israel_palestine | 50 | 0.092 | -2.7% | 0.097 | +1.9% |
| blend:southern_turkey | 20 | 0.095 | -3.1% | 0.095 | +1.7% |
| blend:cyprus | 10 | 0.096 | -3.2% | 0.100 | +2.3% |
| local |  | 0.097 | -3.1% | 0.100 | +2.3% |
| blend:syria | 0 | 0.097 | -3.1% | 0.097 | +1.7% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 1165 | 1203 | 1160.6 | 1.033 | 0.996 | [0.960, 1.055] | no step | [0.982, 1.008] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 9 | 10 | 9.7 |
| 2026-02 | 23 | 23 | 22.2 |
| 2026-03 | 272 | 300 | 289.4 |
| 2026-04 | 223 | 230 | 221.9 |
| 2026-05 | 54 | 50 | 48.2 |
| 2026-06 | 45 | 54 | 52.1 |
| 2026-07 | 154 | 168 | 162.1 |
| 2026-08 | 158 | 142 | 137.0 |
| 2026-09 | 96 | 115 | 110.9 |
| 2026-10 | 105 | 95 | 91.7 |
| 2026-11 | 26 | 16 | 15.4 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 0.97, 2019: 1.01, 2020: 1.06, 2021: 1.01, 2022: 0.98, 2023: 1.01, 2024: 0.98, 2025: 0.99
