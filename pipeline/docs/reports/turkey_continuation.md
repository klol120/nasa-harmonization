# turkey: VIIRS continuation (NOAA20 calibrated to SNPP)

From 2026-11-03 the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: 2026-11-02). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over 2018-2025, on days both satellites have data and no flagged outage, persistent-source fire-days excluded. Strategy used: `single`. 90% bands: year bootstrap (B = 1000).

## Factors

| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |
|---|---|---|---|---|---|
| 1 | 0.947 | [0.926, 0.966] | 4334 | 4499 | 0.963 |
| 2 | 0.947 | [0.926, 0.966] | 3353 | 3614 | 0.928 |
| 3 | 0.947 | [0.926, 0.966] | 3693 | 3850 | 0.959 |
| 4 | 0.947 | [0.926, 0.966] | 2300 | 2531 | 0.909 |
| 5 | 0.947 | [0.926, 0.966] | 2062 | 2278 | 0.905 |
| 6 | 0.947 | [0.926, 0.966] | 9624 | 9868 | 0.975 |
| 7 | 0.947 | [0.926, 0.966] | 8073 | 8633 | 0.935 |
| 8 | 0.947 | [0.926, 0.966] | 11752 | 11901 | 0.987 |
| 9 | 0.947 | [0.926, 0.966] | 17298 | 17948 | 0.964 |
| 10 | 0.947 | [0.926, 0.966] | 22460 | 23761 | 0.945 |
| 11 | 0.947 | [0.926, 0.966] | 15114 | 16704 | 0.905 |
| 12 | 0.947 | [0.926, 0.966] | 7219 | 7673 | 0.941 |

All months pooled (`single`): c = 0.947 [0.926, 0.966].

## Hold-out (monthly totals): fit 2018-2021, test 2022-2025

| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|
| single |  | 0.068 | +3.8% | 0.052 | -3.6% |
| local |  | 0.076 | +3.5% | 0.064 | -3.8% |
| blend:syria | 0 | 0.076 | +3.5% | 0.064 | -3.8% |
| blend:israel_palestine | 0 | 0.076 | +3.5% | 0.064 | -3.8% |
| blend:eastmed_pool_ex_turkey | 0 | 0.076 | +3.5% | 0.072 | -3.9% |
| blend:cyprus | 10 | 0.076 | +3.5% | 0.064 | -4.0% |

## Continuity at the switch

Window 2026-01-01 to 2026-11-02 (after the fit years, before the switch; both satellites observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread of observed / predicted on the overlap to the factor bootstrap.

| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |
|---|---|---|---|---|---|---|---|
| 10213 | 11207 | 10615.5 | 1.097 | 1.039 | [0.998, 1.127] | no step | [1.016, 1.060] |

| month | S-NPP | NOAA-20 | NOAA-20 calibrated |
|---|---|---|---|
| 2026-01 | 119 | 166 | 157.2 |
| 2026-02 | 271 | 298 | 282.3 |
| 2026-03 | 326 | 539 | 510.6 |
| 2026-04 | 144 | 195 | 184.7 |
| 2026-05 | 121 | 152 | 144.0 |
| 2026-06 | 1087 | 1092 | 1034.4 |
| 2026-07 | 1031 | 1192 | 1129.1 |
| 2026-08 | 1238 | 1307 | 1238.0 |
| 2026-09 | 2823 | 3071 | 2908.9 |
| 2026-10 | 3032 | 3172 | 3004.6 |
| 2026-11 | 21 | 23 | 21.8 |

In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: 2018: 0.99, 2019: 0.98, 2020: 0.96, 2021: 0.99, 2022: 1.00, 2023: 0.99, 2024: 1.08, 2025: 0.98
