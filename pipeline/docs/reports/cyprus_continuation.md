# cyprus: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `single`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.832 | [0.760, 0.917] | 15 | 22 | 0.682 |
| 2 | 0.832 | [0.760, 0.917] | 20 | 28 | 0.714 |
| 3 | 0.832 | [0.760, 0.917] | 39 | 44 | 0.886 |
| 4 | 0.832 | [0.760, 0.917] | 205 | 281 | 0.730 |
| 5 | 0.832 | [0.760, 0.917] | 72 | 100 | 0.720 |
| 6 | 0.832 | [0.760, 0.917] | 46 | 55 | 0.836 |
| 7 | 0.832 | [0.760, 0.917] | 88 | 101 | 0.871 |
| 8 | 0.832 | [0.760, 0.917] | 45 | 45 | 1.000 |
| 9 | 0.832 | [0.760, 0.917] | 65 | 58 | 1.121 |
| 10 | 0.832 | [0.760, 0.917] | 44 | 55 | 0.800 |
| 11 | 0.832 | [0.760, 0.917] | 76 | 68 | 1.118 |
| 12 | 0.832 | [0.760, 0.917] | 20 | 26 | 0.769 |

All months pooled (`single`): c = 0.832 [0.760, 0.917].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| blend:southern_turkey | 1e+09 | 0.381 | +19.8% | 0.426 | -9.5% |
| single |  | 0.382 | +21.1% | 0.394 | -17.4% |
| blend:israel_palestine | 50 | 0.401 | +22.1% | 0.425 | -9.4% |
| blend:eastmed_pool_ex_cyprus | 1e+09 | 0.437 | +29.3% | 0.426 | -9.5% |
| local |  | 0.447 | +21.5% | 0.431 | -10.3% |
| blend:syria | 1e+09 | 0.525 | +40.5% | 0.426 | -9.7% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 47 | 69 | 57.4 | 1.468 | 1.222 | [0.938, 1.577] | no step | [1.116, 1.347] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 2 | 2 | 1.7 |
| 2026-02 | 0 | 1 | 0.8 |
| 2026-03 | 3 | 4 | 3.3 |
| 2026-04 | 24 | 47 | 39.1 |
| 2026-05 | 0 | 0 | 0.0 |
| 2026-06 | 4 | 1 | 0.8 |
| 2026-07 | 6 | 5 | 4.2 |
| 2026-08 | 3 | 1 | 0.8 |
| 2026-09 | 3 | 6 | 5.0 |
| 2026-10 | 2 | 2 | 1.7 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 1.16, 2019: 0.76, 2020: 0.86, 2021: 0.88, 2022: 1.12, 2023: 1.21, 2024: 1.16, 2025: 0.92
