# eastmed: validation

Strategy used downstream: `local`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 257813 | 74500 | 3.46 |
| pdf_rules | fire-days 0.01° | 182633 | 70931 | 2.57 |
| pdf_rules | fire-days 0.05° | 129282 | 48392 | 2.67 |
| pdf_rules | fire-days 0.10° | 110329 | 40483 | 2.73 |
| persistence_excluded | detections | 249302 | 74221 | 3.36 |
| persistence_excluded | fire-days 0.01° | 175644 | 70683 | 2.48 |
| persistence_excluded | fire-days 0.05° | 123145 | 48243 | 2.55 |
| persistence_excluded | fire-days 0.10° | 104431 | 40338 | 2.59 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | local |  | 0.158 | -11.0% | 0.196 | +13.4% |
| pdf_rules | single |  | 0.217 | -13.3% | 0.259 | +15.3% |
| persistence_excluded | local |  | 0.154 | -9.6% | 0.180 | +11.5% |
| persistence_excluded | single |  | 0.208 | -11.7% | 0.236 | +13.2% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = 0.958 over 108 of 108 months with both counts > 0
- persistence_excluded: r = 0.966 over 108 of 108 months with both counts > 0

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |
|---|---|---|---|---|---|---|---|
| pdf_rules | 1.029 | [0.922, 1.126] | no step | [0.966, 1.086] | no step | 0.798 | 0.776 |
| persistence_excluded | 1.034 | [0.939, 1.124] | no step | [0.973, 1.087] | no step | 0.802 | 0.776 |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 0.92, 2013: 1.06, 2014: 0.94, 2015: 1.18, 2016: 1.05, 2017: 1.02, 2018: 0.89, 2019: 0.92, 2020: 0.92

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 0.92, 2013: 1.03, 2014: 0.95, 2015: 1.16, 2016: 1.06, 2017: 1.02, 2018: 0.94, 2019: 0.94, 2020: 0.90

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 9841 | 3389 | 2.90 | 6.2 |
| 2013 | 15812 | 6229 | 2.54 | 6.2 |
| 2014 | 9829 | 3468 | 2.83 | 6.2 |
| 2015 | 18926 | 8528 | 2.22 | 6.2 |
| 2016 | 15163 | 6093 | 2.49 | 6.2 |
| 2017 | 13275 | 4937 | 2.69 | 6.2 |
| 2018 | 9621 | 3219 | 2.99 | 6.03 |
| 2019 | 20433 | 6897 | 2.96 | 6.03 |
| 2020 | 16382 | 5597 | 2.93 | 6.03 |
| 2021 | 10423 | 3716 | 2.80 | 6.03 |
| 2022 | 7022 | 2315 | 3.03 | 6.03 |
| 2023 | 13173 | 4523 | 2.91 | 61.03 |
| 2024 | 14505 | 5674 | 2.56 | 61.03 |
| 2025 | 9065 | 3228 | 2.81 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 2.61 | +0.0% | 0.00 | no |
| 2018-2022 | 2.94 | +12.7% | 3.02 | yes |
| 2023-2025 | 2.76 | +5.6% | 1.00 | no |
