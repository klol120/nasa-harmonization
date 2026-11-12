# lebanon: validation

Strategy used downstream: `affine_shape_single_level`. Overlap [2012, 2020].

## Ratio by counting unit (PDF Table 1)

| variant | unit | VIIRS | MODIS | VIIRS/MODIS |
|---|---|---|---|---|
| pdf_rules | detections | 4333 | 642 | 6.75 |
| pdf_rules | fire-days 0.01° | 3481 | 623 | 5.59 |
| pdf_rules | fire-days 0.05° | 3043 | 480 | 6.34 |
| pdf_rules | fire-days 0.10° | 2921 | 446 | 6.55 |
| persistence_excluded | detections | 3882 | 640 | 6.07 |
| persistence_excluded | fire-days 0.01° | 3049 | 621 | 4.91 |
| persistence_excluded | fire-days 0.05° | 2617 | 478 | 5.47 |
| persistence_excluded | fire-days 0.10° | 2516 | 444 | 5.67 |

## Hold-out error of monthly totals (PDF Table 2): fit 2012-2016, test 2017-2020

WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. Blend k is chosen by leave-one-year-out on the fit years only.

| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |
|---|---|---|---|---|---|---|
| pdf_rules | affine_blend:cyprus | 0 | 0.297 | +3.2% | 0.369 | +5.2% |
| pdf_rules | affine_shape_single_level | 0 | 0.378 | -4.9% | 0.418 | +5.2% |
| pdf_rules | blend:israel_palestine | 10 | 0.424 | -17.4% | 0.513 | +2.0% |
| pdf_rules | blend:syria | 20 | 0.465 | -25.2% | 0.486 | -2.6% |
| pdf_rules | blend:cyprus | 20 | 0.472 | -26.7% | 0.682 | +16.8% |
| pdf_rules | pooled:cyprus |  | 0.475 | -23.7% | 0.773 | +22.3% |
| pdf_rules | blend:eastmed_pool | 20 | 0.476 | -32.3% | 0.457 | -7.7% |
| pdf_rules | blend:southern_turkey | 20 | 0.486 | -34.4% | 0.452 | -9.6% |
| pdf_rules | pooled:israel_palestine |  | 0.500 | -19.8% | 0.520 | -7.6% |
| pdf_rules | local |  | 0.569 | +2.6% | 0.679 | +18.9% |
| pdf_rules | donor:israel_palestine |  | 0.573 | -16.4% | 0.603 | -5.4% |
| pdf_rules | pooled:syria |  | 0.575 | -35.2% | 0.508 | -35.0% |
| pdf_rules | donor:syria |  | 0.586 | -35.5% | 0.516 | -35.9% |
| pdf_rules | single |  | 0.599 | -4.9% | 0.592 | +5.2% |
| pdf_rules | pooled:eastmed_pool |  | 0.635 | -58.0% | 0.528 | -50.1% |
| pdf_rules | donor:eastmed_pool |  | 0.638 | -58.5% | 0.533 | -50.5% |
| pdf_rules | pooled:southern_turkey |  | 0.657 | -63.3% | 0.574 | -56.9% |
| pdf_rules | donor:cyprus |  | 0.659 | -44.1% | 0.691 | -25.5% |
| pdf_rules | donor:southern_turkey |  | 0.661 | -64.1% | 0.582 | -57.8% |
| persistence_excluded | affine_blend:cyprus | 0 | 0.283 | +3.2% | 0.373 | -1.0% |
| persistence_excluded | affine_shape_single_level | 0 | 0.338 | -4.7% | 0.417 | +4.9% |
| persistence_excluded | blend:israel_palestine | 10 | 0.414 | -12.7% | 0.498 | +6.3% |
| persistence_excluded | blend:eastmed_pool | 20 | 0.437 | -27.5% | 0.445 | -3.6% |
| persistence_excluded | blend:southern_turkey | 20 | 0.446 | -29.7% | 0.440 | -5.2% |
| persistence_excluded | blend:cyprus | 20 | 0.460 | -21.3% | 0.645 | +15.2% |
| persistence_excluded | blend:syria | 50 | 0.466 | -25.2% | 0.467 | +0.4% |
| persistence_excluded | pooled:israel_palestine |  | 0.470 | -14.2% | 0.503 | -1.7% |
| persistence_excluded | pooled:cyprus |  | 0.472 | -19.1% | 0.725 | +22.8% |
| persistence_excluded | local |  | 0.525 | +2.0% | 0.622 | +19.8% |
| persistence_excluded | donor:israel_palestine |  | 0.537 | -9.8% | 0.595 | +2.0% |
| persistence_excluded | pooled:syria |  | 0.539 | -31.4% | 0.483 | -32.4% |
| persistence_excluded | single |  | 0.547 | -4.7% | 0.532 | +4.9% |
| persistence_excluded | donor:syria |  | 0.549 | -31.8% | 0.493 | -33.3% |
| persistence_excluded | pooled:eastmed_pool |  | 0.593 | -53.0% | 0.491 | -45.0% |
| persistence_excluded | donor:eastmed_pool |  | 0.595 | -53.5% | 0.495 | -45.4% |
| persistence_excluded | pooled:southern_turkey |  | 0.618 | -58.2% | 0.523 | -50.9% |
| persistence_excluded | donor:southern_turkey |  | 0.622 | -59.0% | 0.530 | -51.7% |
| persistence_excluded | donor:cyprus |  | 0.664 | -36.6% | 0.676 | -17.9% |

## Monthly log-count correlation (overlap)

- pdf_rules: r = 0.764 over 68 of 108 months with both counts > 0
- persistence_excluded: r = 0.779 over 68 of 108 months with both counts > 0

## Blend k selection on the full overlap (leave-one-year-out WAPE)

| k | affine_blend:cyprus | blend:cyprus | blend:eastmed_pool | blend:israel_palestine | blend:southern_turkey | blend:syria |
|---|---|---|---|---|---|---|
| 0 | 0.252 | 0.558 | 0.558 | 0.558 | 0.558 | 0.558 |
| 5 | 0.305 | 0.467 | 0.423 | 0.448 | 0.417 | 0.434 |
| 10 | 0.333 | 0.453 | 0.403 | 0.432 | 0.400 | 0.415 |
| 20 | 0.374 | 0.448 | 0.398 | 0.427 | 0.399 | 0.410 |
| 50 | 0.448 | 0.453 | 0.407 | 0.444 | 0.415 | 0.420 |
| 100 | 0.516 | 0.477 | 0.436 | 0.468 | 0.457 | 0.430 |
| 1e+09 | 0.686 | 0.596 | 0.550 | 0.571 | 0.586 | 0.519 |

## Continuity at 2012

Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.

| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |
|---|---|---|---|---|---|---|---|
| pdf_rules | 1.010 | [0.734, 1.319] | no step | [0.844, 1.156] | no step | 0.841 | 0.833 |
| persistence_excluded | 1.025 | [0.771, 1.293] | no step | [0.873, 1.156] | no step | 0.854 | 0.833 |

In-sample Σ Ñ_V / Σ N_V per overlap year (pdf_rules): 2012: 0.84, 2013: 1.35, 2014: 0.56, 2015: 0.91, 2016: 1.18, 2017: 0.81, 2018: 0.72, 2019: 0.79, 2020: 1.39

In-sample Σ Ñ_V / Σ N_V per overlap year (persistence_excluded): 2012: 0.82, 2013: 1.26, 2014: 0.61, 2015: 0.94, 2016: 1.18, 2017: 0.79, 2018: 0.84, 2019: 0.77, 2020: 1.33

## Breaks at MODIS processing changes (report only)

| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |
|---|---|---|---|---|
| 2012 | 293 | 39 | 7.51 | 6.2 |
| 2013 | 469 | 100 | 4.69 | 6.2 |
| 2014 | 294 | 26 | 11.31 | 6.2 |
| 2015 | 314 | 45 | 6.98 | 6.2 |
| 2016 | 425 | 79 | 5.38 | 6.2 |
| 2017 | 242 | 31 | 7.81 | 6.2 |
| 2018 | 254 | 29 | 8.76 | 6.03 |
| 2019 | 354 | 44 | 8.05 | 6.03 |
| 2020 | 398 | 87 | 4.57 | 6.03 |
| 2021 | 537 | 89 | 6.03 | 6.03 |
| 2022 | 278 | 20 | 13.90 | 6.03 |
| 2023 | 366 | 42 | 8.71 | 61.03 |
| 2024 | 625 | 156 | 4.01 | 61.03 |
| 2025 | 340 | 57 | 5.96 | 61.03 |

| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |
|---|---|---|---|---|
| 2012-2017 | 7.28 | +0.0% | 0.00 | no |
| 2018-2022 | 8.26 | +13.5% | 0.53 | no |
| 2023-2025 | 6.23 | -14.4% | -0.63 | no |
