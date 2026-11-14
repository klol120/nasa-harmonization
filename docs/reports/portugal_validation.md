# portugal: validation

Strategy used downstream: `local`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 65450 | 24445 | 2.68 |
| pdf_rules | fire-days 0.01° | 31801 | 21366 | 1.49 |
| pdf_rules | fire-days 0.05° | 17519 | 10030 | 1.75 |
| pdf_rules | fire-days 0.10° | 15278 | 8048 | 1.90 |
| persistence_excluded | detections | 64833 | 24418 | 2.66 |
| persistence_excluded | fire-days 0.01° | 31257 | 21340 | 1.46 |
| persistence_excluded | fire-days 0.05° | 16993 | 10008 | 1.70 |
| persistence_excluded | fire-days 0.10° | 14763 | 8026 | 1.84 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | affine_shape_single_level_pool | 0 | 0.217 | +0.8% | 0.191 | -0.8% |
| pdf_rules | affine_shape_single_level | 0 | 0.217 | +0.8% | 0.188 | -0.8% |
| pdf_rules | pooled:cyprus |  | 0.237 | +16.4% | 0.202 | -2.2% |
| pdf_rules | blend:cyprus | 0 | 0.238 | +12.2% | 0.194 | -5.3% |
| pdf_rules | blend:southern_turkey | 0 | 0.238 | +12.2% | 0.194 | -5.3% |
| pdf_rules | blend:syria | 0 | 0.238 | +12.2% | 0.194 | -5.3% |
| pdf_rules | blend:israel_palestine | 0 | 0.238 | +12.2% | 0.194 | -5.3% |
| pdf_rules | blend:eastmed_pool | 0 | 0.238 | +12.2% | 0.194 | -5.3% |
| pdf_rules | local |  | 0.238 | +12.2% | 0.194 | -5.3% |
| pdf_rules | single |  | 0.308 | +0.8% | 0.276 | -0.8% |
| pdf_rules | pooled:israel_palestine |  | 0.346 | +31.0% | 0.250 | +14.6% |
| pdf_rules | pooled:southern_turkey |  | 0.383 | +24.2% | 0.458 | +33.0% |
| pdf_rules | donor:southern_turkey |  | 0.513 | +36.8% | 0.660 | +53.4% |
| pdf_rules | pooled:eastmed_pool |  | 0.526 | +49.6% | 0.683 | +62.1% |
| pdf_rules | pooled:syria |  | 0.629 | +62.2% | 0.688 | +66.3% |
| pdf_rules | donor:eastmed_pool |  | 0.779 | +75.0% | 0.958 | +90.4% |
| pdf_rules | donor:syria |  | 1.614 | +161.4% | 1.430 | +142.1% |
| pdf_rules | donor:cyprus |  | 2.294 | +226.7% | 4.500 | +445.2% |
| pdf_rules | donor:israel_palestine |  | 2.472 | +247.2% | 2.771 | +276.6% |
| persistence_excluded | affine_shape_single_level | 0 | 0.220 | +1.7% | 0.187 | -1.7% |
| persistence_excluded | affine_shape_single_level_pool | 0 | 0.220 | +1.7% | 0.190 | -1.7% |
| persistence_excluded | local |  | 0.231 | +12.3% | 0.192 | -6.1% |
| persistence_excluded | blend:eastmed_pool | 0 | 0.231 | +12.3% | 0.192 | -6.1% |
| persistence_excluded | blend:israel_palestine | 0 | 0.231 | +12.3% | 0.192 | -6.1% |
| persistence_excluded | blend:syria | 0 | 0.231 | +12.3% | 0.192 | -6.1% |
| persistence_excluded | blend:southern_turkey | 0 | 0.231 | +12.3% | 0.192 | -6.1% |
| persistence_excluded | blend:cyprus | 0 | 0.231 | +12.3% | 0.192 | -6.1% |
| persistence_excluded | pooled:cyprus |  | 0.234 | +16.5% | 0.200 | -3.1% |
| persistence_excluded | single |  | 0.308 | +1.7% | 0.261 | -1.7% |
| persistence_excluded | pooled:israel_palestine |  | 0.337 | +30.0% | 0.234 | +12.6% |
| persistence_excluded | pooled:southern_turkey |  | 0.402 | +25.5% | 0.449 | +33.5% |
| persistence_excluded | pooled:eastmed_pool |  | 0.520 | +48.6% | 0.631 | +56.3% |
| persistence_excluded | donor:southern_turkey |  | 0.537 | +36.9% | 0.651 | +53.4% |
| persistence_excluded | pooled:syria |  | 0.588 | +57.8% | 0.581 | +54.9% |
| persistence_excluded | donor:eastmed_pool |  | 0.750 | +71.9% | 0.865 | +80.9% |
| persistence_excluded | donor:syria |  | 1.475 | +147.5% | 1.186 | +117.5% |
| persistence_excluded | donor:cyprus |  | 2.217 | +219.4% | 4.287 | +423.8% |
| persistence_excluded | donor:israel_palestine |  | 2.300 | +230.0% | 2.466 | +246.1% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = 0.951 over 107 of 108 months with both counts > 0
- persistence_excluded: r = 0.953 over 106 of 108 months with both counts > 0

## Blend k selection on the full overlap (leave-one-year-out WAPE)

| k | blend:cyprus | blend:eastmed_pool | blend:israel_palestine | blend:southern_turkey | blend:syria |
|---|---|---|---|---|---|
| 0 | 0.201 | 0.201 | 0.201 | 0.201 | 0.201 |
| 5 | 0.210 | 0.202 | 0.204 | 0.201 | 0.202 |
| 10 | 0.225 | 0.202 | 0.208 | 0.201 | 0.202 |
| 20 | 0.258 | 0.203 | 0.216 | 0.201 | 0.207 |
| 50 | 0.358 | 0.208 | 0.253 | 0.202 | 0.225 |
| 100 | 0.510 | 0.220 | 0.328 | 0.206 | 0.258 |
| 1e+09 | 2.521 | 0.815 | 2.354 | 0.582 | 1.307 |

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |
|---|---|---|---|---|---|---|---|
| pdf_rules | 1.091 | [0.930, 1.241] | no step | [0.990, 1.149] | no step | 0.776 | 0.711 |
| persistence_excluded | 1.098 | [0.943, 1.242] | no step | [1.001, 1.156] | **step flagged** | 0.781 | 0.711 |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 1.07, 2013: 0.94, 2014: 0.73, 2015: 0.97, 2016: 0.98, 2017: 1.12, 2018: 0.88, 2019: 1.02, 2020: 1.04

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 1.07, 2013: 0.92, 2014: 0.75, 2015: 0.96, 2016: 1.00, 2017: 1.11, 2018: 0.89, 2019: 1.04, 2020: 1.06

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 2669 | 1560 | 1.71 | 6.2 |
| 2013 | 2815 | 1673 | 1.68 | 6.2 |
| 2014 | 918 | 354 | 2.59 | 6.2 |
| 2015 | 2128 | 1081 | 1.97 | 6.2 |
| 2016 | 2256 | 1476 | 1.53 | 6.2 |
| 2017 | 3281 | 2073 | 1.58 | 6.2 |
| 2018 | 1158 | 525 | 2.21 | 6.03 |
| 2019 | 1343 | 693 | 1.94 | 6.03 |
| 2020 | 951 | 575 | 1.65 | 6.03 |
| 2021 | 1073 | 546 | 1.97 | 6.03 |
| 2022 | 1222 | 820 | 1.49 | 6.03 |
| 2023 | 936 | 466 | 2.01 | 61.03 |
| 2024 | 1115 | 795 | 1.40 | 61.03 |
| 2025 | 1435 | 1094 | 1.31 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 1.84 | +0.0% | 0.00 | no |
| 2018-2022 | 1.85 | +0.3% | 0.03 | no |
| 2023-2025 | 1.57 | -14.6% | -0.99 | no |
