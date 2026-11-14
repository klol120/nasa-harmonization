# greece: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `single`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.921 | [0.896, 0.945] | 668 | 766 | 0.872 |
| 2 | 0.921 | [0.896, 0.945] | 1657 | 1826 | 0.907 |
| 3 | 0.921 | [0.896, 0.945] | 1797 | 1934 | 0.929 |
| 4 | 0.921 | [0.896, 0.945] | 713 | 817 | 0.873 |
| 5 | 0.921 | [0.896, 0.945] | 246 | 254 | 0.969 |
| 6 | 0.921 | [0.896, 0.945] | 440 | 467 | 0.942 |
| 7 | 0.921 | [0.896, 0.945] | 912 | 920 | 0.991 |
| 8 | 0.921 | [0.896, 0.945] | 1343 | 1437 | 0.935 |
| 9 | 0.921 | [0.896, 0.945] | 750 | 862 | 0.870 |
| 10 | 0.921 | [0.896, 0.945] | 2278 | 2493 | 0.914 |
| 11 | 0.921 | [0.896, 0.945] | 2203 | 2341 | 0.941 |
| 12 | 0.921 | [0.896, 0.945] | 399 | 446 | 0.895 |

All months pooled (`single`): c = 0.921 [0.896, 0.945].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| single |  | 0.114 | -0.7% | 0.077 | +0.7% |
| blend:southern_turkey | 20 | 0.134 | +0.7% | 0.098 | +1.4% |
| blend:cyprus | 5 | 0.134 | +0.6% | 0.102 | +0.5% |
| blend:eastmed_pool | 20 | 0.134 | +0.8% | 0.104 | +1.6% |
| local |  | 0.135 | +0.6% | 0.103 | +1.2% |
| blend:israel_palestine | 5 | 0.135 | +0.7% | 0.101 | +1.6% |
| blend:syria | 5 | 0.136 | +0.8% | 0.121 | +0.6% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 876 | 1048 | 964.7 | 1.196 | 1.101 | [0.999, 1.207] | no step | [1.072, 1.130] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 29 | 35 | 32.2 |
| 2026-02 | 67 | 46 | 42.4 |
| 2026-03 | 195 | 287 | 264.2 |
| 2026-04 | 57 | 65 | 59.8 |
| 2026-05 | 29 | 35 | 32.2 |
| 2026-06 | 46 | 53 | 48.8 |
| 2026-07 | 86 | 115 | 105.9 |
| 2026-08 | 107 | 119 | 109.5 |
| 2026-09 | 72 | 82 | 75.5 |
| 2026-10 | 187 | 211 | 194.2 |
| 2026-11 | 1 | 0 | 0.0 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 1.04, 2019: 0.97, 2020: 0.98, 2021: 1.04, 2022: 0.99, 2023: 0.99, 2024: 1.09, 2025: 0.91
