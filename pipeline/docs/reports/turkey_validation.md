# turkey: validation

Strategy used downstream: `local`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 272488 | 86029 | 3.17 |
| pdf_rules | fire-days 0.01° | 203789 | 82561 | 2.47 |
| pdf_rules | fire-days 0.05° | 150749 | 59234 | 2.54 |
| pdf_rules | fire-days 0.10° | 131087 | 50961 | 2.57 |
| persistence_excluded | detections | 266443 | 85870 | 3.10 |
| persistence_excluded | fire-days 0.01° | 198369 | 82404 | 2.41 |
| persistence_excluded | fire-days 0.05° | 145606 | 59111 | 2.46 |
| persistence_excluded | fire-days 0.10° | 126149 | 50841 | 2.48 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | pooled:syria |  | 0.135 | -2.4% | 0.242 | +21.7% |
| pdf_rules | pooled:eastmed_pool_ex_turkey |  | 0.137 | -1.0% | 0.258 | +23.5% |
| pdf_rules | affine_shape_single_level_pool_ex_turkey | 5 | 0.139 | -10.0% | 0.185 | +11.1% |
| pdf_rules | affine_shape_single_level | 10 | 0.142 | -10.0% | 0.187 | +11.1% |
| pdf_rules | pooled:israel_palestine |  | 0.146 | -7.4% | 0.191 | +15.0% |
| pdf_rules | blend:syria | 20 | 0.152 | -8.7% | 0.172 | +12.6% |
| pdf_rules | pooled:cyprus |  | 0.152 | -8.9% | 0.174 | +13.0% |
| pdf_rules | blend:eastmed_pool_ex_turkey | 10 | 0.153 | -8.9% | 0.172 | +12.6% |
| pdf_rules | blend:cyprus | 5 | 0.153 | -8.9% | 0.172 | +12.6% |
| pdf_rules | blend:israel_palestine | 0 | 0.153 | -9.2% | 0.172 | +12.6% |
| pdf_rules | local |  | 0.153 | -9.2% | 0.172 | +12.6% |
| pdf_rules | single |  | 0.253 | -10.0% | 0.230 | +11.1% |
| pdf_rules | donor:syria |  | 0.532 | +51.6% | 0.629 | +62.8% |
| pdf_rules | donor:cyprus |  | 0.532 | +39.1% | 1.757 | +167.3% |
| pdf_rules | donor:eastmed_pool_ex_turkey |  | 0.552 | +53.9% | 0.656 | +65.6% |
| pdf_rules | donor:israel_palestine |  | 0.971 | +97.0% | 1.388 | +138.7% |
| persistence_excluded | affine_shape_single_level_pool_ex_turkey | 0 | 0.132 | -8.4% | 0.176 | +9.1% |
| persistence_excluded | pooled:syria |  | 0.132 | -1.2% | 0.210 | +17.7% |
| persistence_excluded | pooled:eastmed_pool_ex_turkey |  | 0.135 | +0.2% | 0.224 | +19.4% |
| persistence_excluded | pooled:israel_palestine |  | 0.138 | -5.8% | 0.174 | +12.7% |
| persistence_excluded | affine_shape_single_level | 20 | 0.139 | -8.4% | 0.176 | +9.1% |
| persistence_excluded | blend:eastmed_pool_ex_turkey | 50 | 0.142 | -6.3% | 0.157 | +10.4% |
| persistence_excluded | blend:syria | 50 | 0.142 | -6.3% | 0.157 | +10.4% |
| persistence_excluded | pooled:cyprus |  | 0.143 | -7.2% | 0.157 | +10.8% |
| persistence_excluded | blend:cyprus | 10 | 0.143 | -7.0% | 0.157 | +10.4% |
| persistence_excluded | blend:israel_palestine | 0 | 0.143 | -7.4% | 0.157 | +10.4% |
| persistence_excluded | local |  | 0.143 | -7.4% | 0.157 | +10.4% |
| persistence_excluded | single |  | 0.256 | -8.4% | 0.234 | +9.1% |
| persistence_excluded | donor:syria |  | 0.476 | +45.8% | 0.487 | +48.7% |
| persistence_excluded | donor:eastmed_pool_ex_turkey |  | 0.503 | +48.7% | 0.526 | +52.5% |
| persistence_excluded | donor:cyprus |  | 0.529 | +39.1% | 1.674 | +158.1% |
| persistence_excluded | donor:israel_palestine |  | 0.911 | +91.0% | 1.254 | +125.4% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = 0.946 over 108 of 108 months with both counts > 0
- persistence_excluded: r = 0.939 over 108 of 108 months with both counts > 0

## Blend k selection on the full overlap (leave-one-year-out WAPE)

| k | blend:cyprus | blend:eastmed_pool_ex_turkey | blend:israel_palestine | blend:syria |
|---|---|---|---|---|
| 0 | 0.123 | 0.123 | 0.123 | 0.123 |
| 5 | 0.122 | 0.123 | 0.123 | 0.123 |
| 10 | 0.122 | 0.123 | 0.123 | 0.123 |
| 20 | 0.123 | 0.123 | 0.123 | 0.123 |
| 50 | 0.131 | 0.123 | 0.123 | 0.123 |
| 100 | 0.146 | 0.123 | 0.126 | 0.123 |
| 1e+09 | 0.680 | 0.526 | 1.086 | 0.492 |

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |
|---|---|---|---|---|---|---|---|
| pdf_rules | 0.956 | [0.873, 1.037] | no step | [0.901, 1.001] | no step | 0.479 | 0.501 |
| persistence_excluded | 0.962 | [0.884, 1.039] | no step | [0.910, 1.003] | no step | 0.481 | 0.500 |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 0.98, 2013: 1.00, 2014: 1.00, 2015: 1.14, 2016: 1.01, 2017: 1.00, 2018: 0.97, 2019: 0.94, 2020: 0.85

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 0.96, 2013: 0.99, 2014: 1.00, 2015: 1.13, 2016: 1.01, 2017: 1.01, 2018: 0.98, 2019: 0.95, 2020: 0.86

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 12179 | 4625 | 2.63 | 6.2 |
| 2013 | 19293 | 7541 | 2.56 | 6.2 |
| 2014 | 11099 | 4481 | 2.48 | 6.2 |
| 2015 | 24988 | 11333 | 2.20 | 6.2 |
| 2016 | 22435 | 8834 | 2.54 | 6.2 |
| 2017 | 15782 | 6305 | 2.50 | 6.2 |
| 2018 | 13074 | 5003 | 2.61 | 6.03 |
| 2019 | 15361 | 5503 | 2.79 | 6.03 |
| 2020 | 16538 | 5579 | 2.96 | 6.03 |
| 2021 | 12151 | 4857 | 2.50 | 6.03 |
| 2022 | 9180 | 3711 | 2.47 | 6.03 |
| 2023 | 15729 | 6027 | 2.61 | 61.03 |
| 2024 | 18076 | 7797 | 2.32 | 61.03 |
| 2025 | 12761 | 5328 | 2.40 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 2.49 | +0.0% | 0.00 | no |
| 2018-2022 | 2.67 | +7.4% | 1.65 | no |
| 2023-2025 | 2.44 | -1.8% | -0.42 | no |
