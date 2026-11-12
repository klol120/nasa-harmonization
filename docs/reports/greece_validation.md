# greece: validation

Strategy used downstream: `local`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 40950 | 12032 | 3.40 |
| pdf_rules | fire-days 0.01° | 29776 | 11328 | 2.63 |
| pdf_rules | fire-days 0.05° | 22283 | 7799 | 2.86 |
| pdf_rules | fire-days 0.10° | 19935 | 6913 | 2.88 |
| persistence_excluded | detections | 40464 | 12031 | 3.36 |
| persistence_excluded | fire-days 0.01° | 29306 | 11327 | 2.59 |
| persistence_excluded | fire-days 0.05° | 21825 | 7799 | 2.80 |
| persistence_excluded | fire-days 0.10° | 19485 | 6913 | 2.82 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | blend:eastmed_pool | 5 | 0.187 | +0.5% | 0.144 | +0.1% |
| pdf_rules | blend:southern_turkey | 5 | 0.188 | +0.1% | 0.142 | -0.5% |
| pdf_rules | blend:israel_palestine | 0 | 0.189 | +0.7% | 0.149 | +0.3% |
| pdf_rules | blend:syria | 0 | 0.189 | +0.7% | 0.149 | +0.3% |
| pdf_rules | blend:cyprus | 0 | 0.189 | +0.7% | 0.149 | +0.3% |
| pdf_rules | local |  | 0.189 | +0.7% | 0.149 | +0.3% |
| pdf_rules | pooled:cyprus |  | 0.196 | +2.2% | 0.157 | +2.1% |
| pdf_rules | pooled:israel_palestine |  | 0.211 | +7.9% | 0.190 | +14.0% |
| pdf_rules | pooled:eastmed_pool |  | 0.227 | -2.1% | 0.243 | +12.4% |
| pdf_rules | pooled:southern_turkey |  | 0.237 | -13.2% | 0.170 | -3.1% |
| pdf_rules | donor:eastmed_pool |  | 0.245 | -1.4% | 0.275 | +14.9% |
| pdf_rules | single |  | 0.261 | -7.0% | 0.230 | +7.5% |
| pdf_rules | pooled:syria |  | 0.262 | +16.1% | 0.338 | +31.2% |
| pdf_rules | donor:southern_turkey |  | 0.279 | -18.3% | 0.213 | -4.8% |
| pdf_rules | donor:syria |  | 0.539 | +48.1% | 0.514 | +50.5% |
| pdf_rules | donor:cyprus |  | 0.721 | +62.7% | 1.569 | +141.7% |
| pdf_rules | donor:israel_palestine |  | 0.980 | +96.0% | 1.150 | +114.1% |
| persistence_excluded | blend:eastmed_pool | 5 | 0.186 | +1.5% | 0.147 | -1.7% |
| persistence_excluded | blend:southern_turkey | 5 | 0.187 | +1.1% | 0.146 | -2.2% |
| persistence_excluded | local |  | 0.188 | +1.8% | 0.152 | -1.5% |
| persistence_excluded | blend:syria | 0 | 0.188 | +1.8% | 0.150 | -0.9% |
| persistence_excluded | blend:israel_palestine | 0 | 0.188 | +1.8% | 0.152 | -1.5% |
| persistence_excluded | blend:cyprus | 0 | 0.188 | +1.8% | 0.152 | -1.5% |
| persistence_excluded | pooled:cyprus |  | 0.194 | +3.2% | 0.159 | +0.3% |
| persistence_excluded | pooled:israel_palestine |  | 0.206 | +7.9% | 0.172 | +11.6% |
| persistence_excluded | pooled:eastmed_pool |  | 0.226 | -3.2% | 0.220 | +8.9% |
| persistence_excluded | pooled:southern_turkey |  | 0.235 | -12.6% | 0.168 | -3.2% |
| persistence_excluded | donor:eastmed_pool |  | 0.244 | -3.4% | 0.250 | +10.3% |
| persistence_excluded | pooled:syria |  | 0.249 | +13.8% | 0.268 | +23.0% |
| persistence_excluded | single |  | 0.265 | -6.2% | 0.221 | +6.6% |
| persistence_excluded | donor:southern_turkey |  | 0.282 | -18.3% | 0.216 | -4.9% |
| persistence_excluded | donor:syria |  | 0.466 | +38.6% | 0.386 | +36.3% |
| persistence_excluded | donor:cyprus |  | 0.698 | +60.6% | 1.467 | +131.0% |
| persistence_excluded | donor:israel_palestine |  | 0.849 | +83.0% | 1.018 | +100.0% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = 0.943 over 108 of 108 months with both counts > 0
- persistence_excluded: r = 0.940 over 108 of 108 months with both counts > 0

## Blend k selection on the full overlap (leave-one-year-out WAPE)

| k | blend:cyprus | blend:eastmed_pool | blend:israel_palestine | blend:southern_turkey | blend:syria |
|---|---|---|---|---|---|
| 0 | 0.139 | 0.139 | 0.139 | 0.139 | 0.139 |
| 5 | 0.145 | 0.138 | 0.139 | 0.138 | 0.139 |
| 10 | 0.151 | 0.138 | 0.140 | 0.137 | 0.139 |
| 20 | 0.169 | 0.137 | 0.141 | 0.136 | 0.140 |
| 50 | 0.222 | 0.137 | 0.151 | 0.137 | 0.141 |
| 100 | 0.292 | 0.140 | 0.178 | 0.142 | 0.145 |
| 1e+09 | 0.873 | 0.227 | 0.925 | 0.222 | 0.421 |

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band | harmonized step | MODIS step | result |
|---|---|---|---|---|---|
| pdf_rules | 1.012 | [0.960, 1.067] | 1.001 | 0.988 | no step |
| persistence_excluded | 1.020 | [0.967, 1.075] | 1.008 | 0.989 | no step |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 1.01, 2013: 1.01, 2014: 0.98, 2015: 0.99, 2016: 0.99, 2017: 1.04, 2018: 1.03, 2019: 0.89, 2020: 1.05

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 1.01, 2013: 1.01, 2014: 0.97, 2015: 0.99, 2016: 0.99, 2017: 1.04, 2018: 1.05, 2019: 0.90, 2020: 1.05

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 3182 | 1161 | 2.74 | 6.2 |
| 2013 | 3138 | 1168 | 2.69 | 6.2 |
| 2014 | 2375 | 860 | 2.76 | 6.2 |
| 2015 | 2463 | 845 | 2.91 | 6.2 |
| 2016 | 2787 | 972 | 2.87 | 6.2 |
| 2017 | 2516 | 909 | 2.77 | 6.2 |
| 2018 | 1552 | 521 | 2.98 | 6.03 |
| 2019 | 2171 | 634 | 3.42 | 6.03 |
| 2020 | 2099 | 722 | 2.91 | 6.03 |
| 2021 | 1706 | 721 | 2.37 | 6.03 |
| 2022 | 1889 | 641 | 2.95 | 6.03 |
| 2023 | 1818 | 837 | 2.17 | 61.03 |
| 2024 | 1490 | 609 | 2.45 | 61.03 |
| 2025 | 1391 | 512 | 2.72 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 2.79 | +0.0% | 0.00 | no |
| 2018-2022 | 2.92 | +4.8% | 0.79 | no |
| 2023-2025 | 2.45 | -12.4% | -2.14 | yes |
