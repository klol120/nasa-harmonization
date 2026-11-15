# jordan: validation

Strategy used downstream: `affine_shape_single_level_pool`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 2900 | 354 | 8.19 |
| pdf_rules | fire-days 0.01° | 2441 | 351 | 6.95 |
| pdf_rules | fire-days 0.05° | 2228 | 294 | 7.58 |
| pdf_rules | fire-days 0.10° | 2197 | 289 | 7.60 |
| persistence_excluded | detections | 2388 | 350 | 6.82 |
| persistence_excluded | fire-days 0.01° | 1979 | 347 | 5.70 |
| persistence_excluded | fire-days 0.05° | 1784 | 290 | 6.15 |
| persistence_excluded | fire-days 0.10° | 1755 | 285 | 6.16 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | affine_blend:eastmed_pool | 0 | 0.442 | +0.4% | 0.315 | +5.0% |
| pdf_rules | affine_shape_single_level_pool | 0 | 0.444 | +13.4% | 0.486 | -11.8% |
| pdf_rules | affine_shape_single_level | 0 | 0.444 | +13.4% | 0.486 | -11.8% |
| pdf_rules | blend:southern_turkey | 20 | 0.694 | -38.8% | 0.683 | -18.4% |
| pdf_rules | blend:eastmed_pool | 20 | 0.707 | -33.0% | 0.682 | -15.7% |
| pdf_rules | blend:syria | 20 | 0.730 | -21.2% | 0.714 | -9.2% |
| pdf_rules | blend:israel_palestine | 50 | 0.771 | -16.8% | 0.710 | -4.2% |
| pdf_rules | pooled:israel_palestine |  | 0.784 | -19.2% | 0.648 | -30.8% |
| pdf_rules | pooled:syria |  | 0.785 | -38.6% | 0.783 | -41.4% |
| pdf_rules | donor:syria |  | 0.788 | -39.3% | 0.836 | -36.6% |
| pdf_rules | donor:israel_palestine |  | 0.808 | -22.4% | 0.700 | -27.2% |
| pdf_rules | pooled:eastmed_pool |  | 0.811 | -57.8% | 0.710 | -63.0% |
| pdf_rules | donor:eastmed_pool |  | 0.812 | -58.4% | 0.713 | -63.3% |
| pdf_rules | pooled:southern_turkey |  | 0.840 | -65.9% | 0.760 | -70.4% |
| pdf_rules | donor:southern_turkey |  | 0.845 | -67.3% | 0.768 | -71.3% |
| pdf_rules | single |  | 0.895 | +13.4% | 0.771 | -11.8% |
| pdf_rules | blend:cyprus | 10 | 0.901 | +2.1% | 0.897 | +19.4% |
| pdf_rules | pooled:cyprus |  | 0.938 | -6.3% | 0.707 | -12.9% |
| pdf_rules | local |  | 0.941 | +26.7% | 0.897 | +19.4% |
| pdf_rules | donor:cyprus |  | 1.108 | -16.6% | 1.388 | +25.2% |
| persistence_excluded | affine_shape_single_level | 0 | 0.466 | +18.9% | 0.518 | -15.9% |
| persistence_excluded | affine_shape_single_level_pool | 0 | 0.466 | +18.9% | 0.518 | -15.9% |
| persistence_excluded | affine_blend:eastmed_pool | 0 | 0.487 | +5.4% | 0.348 | +0.5% |
| persistence_excluded | blend:southern_turkey | 20 | 0.684 | -32.7% | 0.682 | -20.7% |
| persistence_excluded | blend:eastmed_pool | 20 | 0.698 | -26.1% | 0.683 | -18.2% |
| persistence_excluded | blend:syria | 20 | 0.729 | -13.0% | 0.710 | -13.0% |
| persistence_excluded | blend:israel_palestine | 20 | 0.753 | -2.3% | 0.716 | -6.0% |
| persistence_excluded | pooled:israel_palestine |  | 0.778 | -10.3% | 0.662 | -27.2% |
| persistence_excluded | pooled:syria |  | 0.783 | -28.6% | 0.744 | -42.2% |
| persistence_excluded | donor:syria |  | 0.793 | -28.6% | 0.787 | -38.1% |
| persistence_excluded | donor:israel_palestine |  | 0.800 | -12.0% | 0.716 | -20.7% |
| persistence_excluded | pooled:eastmed_pool |  | 0.811 | -49.3% | 0.700 | -59.0% |
| persistence_excluded | donor:eastmed_pool |  | 0.811 | -49.8% | 0.703 | -59.2% |
| persistence_excluded | pooled:southern_turkey |  | 0.837 | -58.5% | 0.740 | -65.7% |
| persistence_excluded | donor:southern_turkey |  | 0.842 | -59.8% | 0.748 | -66.3% |
| persistence_excluded | single |  | 0.889 | +18.9% | 0.762 | -15.9% |
| persistence_excluded | pooled:cyprus |  | 0.933 | +1.8% | 0.728 | -11.4% |
| persistence_excluded | blend:cyprus | 20 | 0.969 | +7.0% | 0.832 | +11.5% |
| persistence_excluded | local |  | 0.990 | +34.5% | 0.832 | +11.5% |
| persistence_excluded | donor:cyprus |  | 1.144 | -2.3% | 1.465 | +40.2% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = -0.079 over 85 of 108 months with both counts > 0
- persistence_excluded: r = -0.070 over 85 of 108 months with both counts > 0

## Blend k selection on the full overlap (leave-one-year-out WAPE)

| k | affine_blend:eastmed_pool | blend:cyprus | blend:eastmed_pool | blend:israel_palestine | blend:southern_turkey | blend:syria |
|---|---|---|---|---|---|---|
| 0 | 0.357 | 0.813 | 0.813 | 0.813 | 0.813 | 0.813 |
| 5 | 0.748 | 0.763 | 0.676 | 0.708 | 0.668 | 0.695 |
| 10 | 1.051 | 0.789 | 0.643 | 0.692 | 0.632 | 0.673 |
| 20 | 1.428 | 0.835 | 0.626 | 0.683 | 0.620 | 0.662 |
| 50 | 1.930 | 0.928 | 0.653 | 0.695 | 0.654 | 0.692 |
| 100 | 2.214 | 0.988 | 0.675 | 0.718 | 0.695 | 0.719 |
| 1e+09 | 2.625 | 1.103 | 0.753 | 0.765 | 0.792 | 0.779 |

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |
|---|---|---|---|---|---|---|---|
| pdf_rules | 1.701 | [0.990, 2.735] | no step | [1.348, 2.093] | **step flagged** | 1.474 | 0.867 |
| persistence_excluded | 1.733 | [0.977, 2.879] | no step | [1.349, 2.129] | **step flagged** | 1.502 | 0.867 |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 0.39, 2013: 0.53, 2014: 0.86, 2015: 1.68, 2016: 1.06, 2017: 1.47, 2018: 1.10, 2019: 1.16, 2020: 0.79

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 0.37, 2013: 0.53, 2014: 0.85, 2015: 1.67, 2016: 1.03, 2017: 1.64, 2018: 1.09, 2019: 1.04, 2020: 0.87

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 212 | 11 | 19.27 | 6.2 |
| 2013 | 245 | 17 | 14.41 | 6.2 |
| 2014 | 212 | 24 | 8.83 | 6.2 |
| 2015 | 274 | 61 | 4.49 | 6.2 |
| 2016 | 243 | 34 | 7.15 | 6.2 |
| 2017 | 201 | 39 | 5.15 | 6.2 |
| 2018 | 179 | 26 | 6.88 | 6.03 |
| 2019 | 267 | 41 | 6.51 | 6.03 |
| 2020 | 395 | 41 | 9.63 | 6.03 |
| 2021 | 321 | 29 | 11.07 | 6.03 |
| 2022 | 257 | 21 | 12.24 | 6.03 |
| 2023 | 276 | 25 | 11.04 | 61.03 |
| 2024 | 367 | 46 | 7.98 | 61.03 |
| 2025 | 273 | 51 | 5.35 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 9.89 | +0.0% | 0.00 | no |
| 2018-2022 | 9.27 | -6.2% | -0.24 | no |
| 2023-2025 | 8.12 | -17.8% | -0.61 | no |
