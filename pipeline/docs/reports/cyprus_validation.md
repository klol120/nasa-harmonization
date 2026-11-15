# cyprus: validation

Strategy used downstream: `affine_shape_single_level_pool_ex_cyprus`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 1985 | 401 | 4.95 |
| pdf_rules | fire-days 0.01° | 1430 | 377 | 3.79 |
| pdf_rules | fire-days 0.05° | 1055 | 253 | 4.17 |
| pdf_rules | fire-days 0.10° | 939 | 226 | 4.15 |
| persistence_excluded | detections | 1913 | 400 | 4.78 |
| persistence_excluded | fire-days 0.01° | 1368 | 376 | 3.64 |
| persistence_excluded | fire-days 0.05° | 1001 | 252 | 3.97 |
| persistence_excluded | fire-days 0.10° | 894 | 225 | 3.97 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | affine_shape_single_level_pool_ex_cyprus | 10 | 0.563 | -13.8% | 0.614 | +16.0% |
| pdf_rules | affine_blend:eastmed_pool_ex_cyprus | 10 | 0.597 | -2.3% | 0.547 | -30.8% |
| pdf_rules | pooled:southern_turkey |  | 0.675 | -52.4% | 0.530 | -39.5% |
| pdf_rules | donor:southern_turkey |  | 0.678 | -52.8% | 0.538 | -40.4% |
| pdf_rules | donor:eastmed_pool_ex_cyprus |  | 0.679 | -43.7% | 0.521 | -27.2% |
| pdf_rules | pooled:eastmed_pool_ex_cyprus |  | 0.680 | -43.5% | 0.518 | -26.8% |
| pdf_rules | blend:eastmed_pool_ex_cyprus | 20 | 0.716 | -35.3% | 0.521 | -27.2% |
| pdf_rules | blend:southern_turkey | 10 | 0.716 | -35.6% | 0.538 | -40.4% |
| pdf_rules | blend:syria | 10 | 0.801 | -19.3% | 0.711 | +9.3% |
| pdf_rules | single |  | 0.824 | -13.8% | 0.819 | +16.0% |
| pdf_rules | blend:israel_palestine | 5 | 0.825 | -15.3% | 0.780 | +28.9% |
| pdf_rules | local |  | 0.832 | -17.7% | 1.325 | +77.3% |
| pdf_rules | pooled:syria |  | 0.844 | -11.4% | 0.734 | +10.0% |
| pdf_rules | donor:syria |  | 0.852 | -10.5% | 0.758 | +11.0% |
| pdf_rules | pooled:israel_palestine |  | 0.923 | -0.5% | 0.848 | +43.2% |
| pdf_rules | donor:israel_palestine |  | 1.004 | +9.1% | 0.921 | +42.4% |
| persistence_excluded | affine_shape_single_level_pool_ex_cyprus | 10 | 0.559 | -14.0% | 0.648 | +16.3% |
| persistence_excluded | affine_blend:eastmed_pool_ex_cyprus | 10 | 0.587 | -3.7% | 0.566 | -31.0% |
| persistence_excluded | donor:eastmed_pool_ex_cyprus |  | 0.667 | -43.1% | 0.561 | -28.1% |
| persistence_excluded | pooled:eastmed_pool_ex_cyprus |  | 0.668 | -42.9% | 0.558 | -27.7% |
| persistence_excluded | pooled:southern_turkey |  | 0.674 | -51.1% | 0.552 | -37.8% |
| persistence_excluded | donor:southern_turkey |  | 0.677 | -51.5% | 0.558 | -38.7% |
| persistence_excluded | blend:eastmed_pool_ex_cyprus | 20 | 0.701 | -34.8% | 0.561 | -28.1% |
| persistence_excluded | blend:southern_turkey | 10 | 0.702 | -35.0% | 0.558 | -38.7% |
| persistence_excluded | blend:syria | 10 | 0.774 | -20.1% | 0.684 | -0.7% |
| persistence_excluded | pooled:syria |  | 0.800 | -14.3% | 0.692 | -0.6% |
| persistence_excluded | donor:syria |  | 0.805 | -13.7% | 0.709 | -0.2% |
| persistence_excluded | blend:israel_palestine | 5 | 0.806 | -15.6% | 0.802 | +25.5% |
| persistence_excluded | single |  | 0.806 | -14.0% | 0.839 | +16.3% |
| persistence_excluded | local |  | 0.814 | -17.9% | 1.320 | +75.0% |
| persistence_excluded | pooled:israel_palestine |  | 0.885 | -2.2% | 0.856 | +38.9% |
| persistence_excluded | donor:israel_palestine |  | 0.959 | +6.7% | 0.937 | +37.9% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = 0.482 over 74 of 108 months with both counts > 0
- persistence_excluded: r = 0.480 over 73 of 108 months with both counts > 0

## Blend k selection on the full overlap (leave-one-year-out WAPE)

| k | affine_blend:eastmed_pool_ex_cyprus | blend:eastmed_pool_ex_cyprus | blend:israel_palestine | blend:southern_turkey | blend:syria |
|---|---|---|---|---|---|
| 0 | 0.557 | 0.821 | 0.821 | 0.821 | 0.821 |
| 5 | 0.514 | 0.652 | 0.702 | 0.643 | 0.670 |
| 10 | 0.512 | 0.630 | 0.720 | 0.619 | 0.657 |
| 20 | 0.534 | 0.613 | 0.756 | 0.598 | 0.656 |
| 50 | 0.570 | 0.597 | 0.821 | 0.588 | 0.667 |
| 100 | 0.593 | 0.596 | 0.867 | 0.591 | 0.679 |
| 1e+09 | 0.626 | 0.593 | 0.944 | 0.597 | 0.705 |

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |
|---|---|---|---|---|---|---|---|
| pdf_rules | 0.989 | [0.763, 1.298] | no step | [0.885, 1.083] | no step | 1.183 | 1.195 |
| persistence_excluded | 0.971 | [0.740, 1.277] | no step | [0.863, 1.064] | no step | 1.161 | 1.195 |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 0.92, 2013: 1.08, 2014: 0.98, 2015: 1.27, 2016: 0.99, 2017: 0.74, 2018: 1.15, 2019: 0.59, 2020: 1.24

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 0.90, 2013: 1.10, 2014: 1.03, 2015: 1.25, 2016: 0.95, 2017: 0.72, 2018: 1.20, 2019: 0.59, 2020: 1.20

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 95 | 21 | 4.52 | 6.2 |
| 2013 | 190 | 49 | 3.88 | 6.2 |
| 2014 | 145 | 34 | 4.26 | 6.2 |
| 2015 | 125 | 38 | 3.29 | 6.2 |
| 2016 | 131 | 31 | 4.23 | 6.2 |
| 2017 | 102 | 18 | 5.67 | 6.2 |
| 2018 | 80 | 22 | 3.64 | 6.03 |
| 2019 | 99 | 14 | 7.07 | 6.03 |
| 2020 | 88 | 26 | 3.38 | 6.03 |
| 2021 | 98 | 53 | 1.85 | 6.03 |
| 2022 | 76 | 19 | 4.00 | 6.03 |
| 2023 | 103 | 28 | 3.68 | 61.03 |
| 2024 | 101 | 31 | 3.26 | 61.03 |
| 2025 | 136 | 44 | 3.09 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 4.31 | +0.0% | 0.00 | no |
| 2018-2022 | 3.99 | -7.4% | -0.35 | no |
| 2023-2025 | 3.34 | -22.4% | -2.63 | yes |
