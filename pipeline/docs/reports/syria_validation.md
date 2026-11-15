# syria: validation

Strategy used downstream: `local`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 90086 | 18205 | 4.95 |
| pdf_rules | fire-days 0.01° | 60585 | 16989 | 3.57 |
| pdf_rules | fire-days 0.05° | 43811 | 11596 | 3.78 |
| pdf_rules | fire-days 0.10° | 39336 | 10278 | 3.83 |
| persistence_excluded | detections | 84282 | 17999 | 4.68 |
| persistence_excluded | fire-days 0.01° | 55915 | 16813 | 3.33 |
| persistence_excluded | fire-days 0.05° | 39836 | 11503 | 3.46 |
| persistence_excluded | fire-days 0.10° | 35507 | 10188 | 3.49 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | blend:southern_turkey | 100 | 0.259 | -2.0% | 0.234 | -12.4% |
| pdf_rules | affine_shape_single_level_pool_ex_syria | 50 | 0.260 | +3.8% | 0.201 | -3.7% |
| pdf_rules | blend:eastmed_pool_ex_syria | 100 | 0.266 | -0.9% | 0.378 | -37.3% |
| pdf_rules | affine_shape_single_level | 0 | 0.268 | +3.8% | 0.197 | -3.7% |
| pdf_rules | single |  | 0.294 | +3.8% | 0.275 | -3.7% |
| pdf_rules | pooled:eastmed_pool_ex_syria |  | 0.330 | -29.9% | 0.302 | -27.1% |
| pdf_rules | local |  | 0.332 | +8.4% | 0.267 | -3.2% |
| pdf_rules | pooled:cyprus |  | 0.333 | +8.3% | 0.266 | -3.0% |
| pdf_rules | pooled:southern_turkey |  | 0.339 | -32.1% | 0.313 | -29.2% |
| pdf_rules | blend:israel_palestine | 20 | 0.340 | +9.7% | 0.278 | +0.3% |
| pdf_rules | blend:cyprus | 10 | 0.340 | +9.2% | 0.267 | -3.2% |
| pdf_rules | pooled:israel_palestine |  | 0.350 | +11.1% | 0.272 | -0.9% |
| pdf_rules | donor:eastmed_pool_ex_syria |  | 0.406 | -40.1% | 0.378 | -37.3% |
| pdf_rules | donor:southern_turkey |  | 0.446 | -44.5% | 0.422 | -42.0% |
| pdf_rules | donor:cyprus |  | 0.571 | +9.4% | 1.067 | +71.3% |
| pdf_rules | donor:israel_palestine |  | 0.601 | +44.1% | 0.554 | +43.3% |
| persistence_excluded | blend:southern_turkey | 100 | 0.209 | +1.1% | 0.215 | -14.6% |
| persistence_excluded | blend:eastmed_pool_ex_syria | 100 | 0.216 | +2.2% | 0.212 | -13.6% |
| persistence_excluded | affine_shape_single_level_pool_ex_syria | 20 | 0.234 | +7.4% | 0.180 | -6.9% |
| persistence_excluded | affine_shape_single_level | 0 | 0.238 | +7.4% | 0.166 | -6.9% |
| persistence_excluded | single |  | 0.249 | +7.4% | 0.241 | -6.9% |
| persistence_excluded | local |  | 0.275 | +11.0% | 0.229 | -7.8% |
| persistence_excluded | pooled:cyprus |  | 0.277 | +11.0% | 0.230 | -7.3% |
| persistence_excluded | blend:israel_palestine | 10 | 0.279 | +11.7% | 0.232 | -5.9% |
| persistence_excluded | blend:cyprus | 5 | 0.279 | +11.4% | 0.229 | -7.8% |
| persistence_excluded | pooled:eastmed_pool_ex_syria |  | 0.285 | -25.6% | 0.288 | -26.7% |
| persistence_excluded | pooled:southern_turkey |  | 0.294 | -27.9% | 0.303 | -28.8% |
| persistence_excluded | pooled:israel_palestine |  | 0.296 | +14.1% | 0.232 | -5.0% |
| persistence_excluded | donor:eastmed_pool_ex_syria |  | 0.360 | -35.6% | 0.356 | -34.7% |
| persistence_excluded | donor:southern_turkey |  | 0.402 | -40.1% | 0.400 | -39.3% |
| persistence_excluded | donor:cyprus |  | 0.546 | +13.1% | 1.061 | +74.2% |
| persistence_excluded | donor:israel_palestine |  | 0.576 | +49.1% | 0.509 | +40.9% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = 0.885 over 107 of 108 months with both counts > 0
- persistence_excluded: r = 0.915 over 107 of 108 months with both counts > 0

## Blend k selection on the full overlap (leave-one-year-out WAPE)

| k | blend:cyprus | blend:eastmed_pool_ex_syria | blend:israel_palestine | blend:southern_turkey |
|---|---|---|---|---|
| 0 | 0.274 | 0.274 | 0.274 | 0.274 |
| 5 | 0.277 | 0.271 | 0.275 | 0.271 |
| 10 | 0.279 | 0.269 | 0.275 | 0.268 |
| 20 | 0.285 | 0.265 | 0.277 | 0.264 |
| 50 | 0.303 | 0.254 | 0.281 | 0.252 |
| 100 | 0.326 | 0.242 | 0.290 | 0.238 |
| 1e+09 | 0.555 | 0.362 | 0.563 | 0.404 |

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |
|---|---|---|---|---|---|---|---|
| pdf_rules | 1.170 | [0.839, 1.596] | no step | [0.989, 1.256] | no step | 1.479 | 1.264 |
| persistence_excluded | 1.187 | [0.927, 1.464] | no step | [1.039, 1.273] | **step flagged** | 1.510 | 1.272 |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 0.77, 2013: 1.16, 2014: 0.70, 2015: 1.04, 2016: 0.98, 2017: 0.95, 2018: 0.43, 2019: 1.16, 2020: 1.08

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 0.78, 2013: 1.07, 2014: 0.73, 2015: 1.03, 2016: 0.97, 2017: 0.93, 2018: 0.57, 2019: 1.16, 2020: 1.03

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 3446 | 723 | 4.77 | 6.2 |
| 2013 | 5118 | 1558 | 3.28 | 6.2 |
| 2014 | 2664 | 494 | 5.39 | 6.2 |
| 2015 | 4567 | 1325 | 3.45 | 6.2 |
| 2016 | 3584 | 912 | 3.93 | 6.2 |
| 2017 | 3962 | 858 | 4.62 | 6.2 |
| 2018 | 2763 | 326 | 8.48 | 6.03 |
| 2019 | 11735 | 3628 | 3.23 | 6.03 |
| 2020 | 5972 | 1766 | 3.38 | 6.03 |
| 2021 | 1942 | 361 | 5.38 | 6.03 |
| 2022 | 1460 | 220 | 6.64 | 6.03 |
| 2023 | 3459 | 923 | 3.75 | 61.03 |
| 2024 | 4074 | 1313 | 3.10 | 61.03 |
| 2025 | 1662 | 500 | 3.32 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 4.24 | +0.0% | 0.00 | no |
| 2018-2022 | 5.42 | +27.9% | 1.13 | no |
| 2023-2025 | 3.39 | -20.0% | -2.20 | yes |
