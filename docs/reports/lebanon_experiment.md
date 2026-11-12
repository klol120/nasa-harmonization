# lebanon: ratio vs affine transfer (experiment, before Phase 5)

Persistence rule: persistent cells excluded from fitting (local and donors). Hold-out fit [2012, 2016], test [2017, 2020]; k chosen by leave-one-year-out on the fit years (on the overlap for continuity).

Affine donor intercepts are scaled by footprint size: lebanon has 390 cells; scale = cyprus 1.822, southern_turkey 0.058, syria 0.053, israel_palestine 0.366, eastmed_pool 0.025.

Ranked by: continuity flagged under the new band (no first), then |step index − 1| + |forward bias|, then forward WAPE.

| rank | strategy | step index | old band (factor bootstrap) | new band (+ year spread) | forward bias | forward WAPE | reverse bias | reverse WAPE | in-sample pred/obs | k (fwd / overlap) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | local | 1.033 | [0.78, 1.14] ok | [0.71, 1.28] ok | +2.0% | 0.525 | +19.8% | 0.622 | 1.00 |  |
| 2 | single | 1.025 | [0.87, 1.16] ok | [0.77, 1.29] ok | -4.7% | 0.547 | +4.9% | 0.532 | 1.00 |  |
| 3 | affine_blend:cyprus | 1.138 | [1.03, 1.22] **flag** | [0.98, 1.26] ok | +3.2% | 0.283 | -1.0% | 0.373 | 1.00 | 0 / 0 |
| 4 | donor:israel_palestine | 1.138 | [1.01, 1.23] **flag** | [0.89, 1.39] ok | -9.8% | 0.537 | +2.0% | 0.595 | 0.95 |  |
| 5 | blend:israel_palestine | 1.126 | [1.00, 1.19] **flag** | [0.87, 1.36] ok | -12.7% | 0.414 | +6.3% | 0.498 | 0.91 | 10 / 20 |
| 6 | pooled:israel_palestine | 1.184 | [1.06, 1.26] **flag** | [0.92, 1.44] ok | -14.2% | 0.470 | -1.7% | 0.503 | 0.89 |  |
| 7 | blend:syria | 1.200 | [1.07, 1.26] **flag** | [0.93, 1.45] ok | -25.2% | 0.466 | +0.4% | 0.467 | 0.85 | 50 / 20 |
| 8 | affine_local | 1.138 | [1.08, 1.23] **flag** | [1.02, 1.27] **flag** | +3.2% | 0.283 | -3.3% | 0.298 | 1.00 |  |
| 9 | affine_blend_a:cyprus | 1.150 | [1.10, 1.23] **flag** | [1.03, 1.29] **flag** | +2.3% | 0.278 | -6.8% | 0.243 | 1.00 | 5 / 10 |
| 10 | affine_blend:israel_palestine | 1.187 | [1.12, 1.26] **flag** | [1.07, 1.32] **flag** | -0.1% | 0.281 | -2.8% | 0.294 | 0.96 | 5 / 10 |
| 11 | affine_blend_a:syria | 1.154 | [1.09, 1.20] **flag** | [1.03, 1.27] **flag** | +4.5% | 0.278 | -3.2% | 0.259 | 1.00 | 10 / 20 |
| 12 | affine_blend_a:israel_palestine | 1.159 | [1.09, 1.24] **flag** | [1.03, 1.31] **flag** | +5.2% | 0.260 | -3.3% | 0.261 | 1.00 | 20 / 50 |
| 13 | affine_blend:southern_turkey | 1.205 | [1.14, 1.29] **flag** | [1.07, 1.34] **flag** | +3.2% | 0.283 | -12.2% | 0.294 | 0.94 | 0 / 5 |
| 14 | affine_blend:syria | 1.217 | [1.15, 1.29] **flag** | [1.09, 1.34] **flag** | -3.3% | 0.269 | -9.5% | 0.273 | 0.94 | 5 / 10 |
| 15 | affine_blend_a:eastmed_pool | 1.165 | [1.11, 1.22] **flag** | [1.03, 1.29] **flag** | +9.0% | 0.255 | -4.9% | 0.249 | 1.00 | 1e+09 / 50 |
| 16 | affine_blend:eastmed_pool | 1.205 | [1.14, 1.29] **flag** | [1.08, 1.34] **flag** | -5.9% | 0.272 | -12.3% | 0.295 | 0.94 | 5 / 5 |
| 17 | affine_blend_a:southern_turkey | 1.188 | [1.12, 1.26] **flag** | [1.04, 1.33] **flag** | +9.3% | 0.255 | -6.6% | 0.240 | 1.00 | 1e+09 / 1e+09 |
| 18 | blend:cyprus | 1.260 | [1.13, 1.32] **flag** | [1.02, 1.52] **flag** | -21.3% | 0.460 | +15.2% | 0.645 | 0.87 | 20 / 20 |
| 19 | pooled:cyprus | 1.320 | [1.15, 1.40] **flag** | [1.05, 1.59] **flag** | -19.1% | 0.472 | +22.8% | 0.725 | 0.85 |  |
| 20 | blend:eastmed_pool | 1.284 | [1.17, 1.35] **flag** | [1.01, 1.56] **flag** | -27.5% | 0.437 | -3.6% | 0.445 | 0.81 | 20 / 20 |
| 21 | blend:southern_turkey | 1.310 | [1.20, 1.38] **flag** | [1.02, 1.62] **flag** | -29.7% | 0.446 | -5.2% | 0.440 | 0.79 | 20 / 20 |
| 22 | pooled:syria | 1.534 | [1.26, 1.67] **flag** | [1.11, 1.90] **flag** | -31.4% | 0.539 | -32.4% | 0.483 | 0.68 |  |
| 23 | donor:syria | 1.544 | [1.25, 1.69] **flag** | [1.10, 1.93] **flag** | -31.8% | 0.549 | -33.3% | 0.493 | 0.67 |  |
| 24 | donor:cyprus | 1.888 | [1.60, 2.15] **flag** | [1.41, 2.35] **flag** | -36.6% | 0.664 | -17.9% | 0.676 | 0.63 |  |
| 25 | pooled:eastmed_pool | 2.121 | [1.99, 2.24] **flag** | [1.64, 2.62] **flag** | -53.0% | 0.593 | -45.0% | 0.491 | 0.51 |  |
| 26 | donor:eastmed_pool | 2.137 | [2.00, 2.26] **flag** | [1.62, 2.64] **flag** | -53.5% | 0.595 | -45.4% | 0.495 | 0.50 |  |
| 27 | pooled:southern_turkey | 2.407 | [2.25, 2.53] **flag** | [1.81, 3.03] **flag** | -58.2% | 0.618 | -50.9% | 0.523 | 0.45 |  |
| 28 | donor:southern_turkey | 2.444 | [2.29, 2.56] **flag** | [1.85, 3.08] **flag** | -59.0% | 0.622 | -51.7% | 0.530 | 0.44 |  |

## Hold-out bias by year

bias = (pred − obs) / obs for each test year.

| strategy | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 |
|---|---|---|---|---|---|---|---|---|---|
| local | +4% | +60% | -31% | +15% | +20% | -14% | +49% | -34% | +19% |
| single | -15% | +30% | -37% | -3% | +22% | -23% | -17% | -25% | +30% |
| affine_blend:cyprus | +1% | -6% | +1% | +12% | -7% | +8% | +19% | -16% | +9% |
| donor:israel_palestine | -8% | +24% | -30% | -4% | +7% | -27% | -21% | -31% | +25% |
| blend:eastmed_pool | -11% | +18% | -36% | +4% | -9% | -42% | -28% | -44% | -4% |
| *observed VIIRS fire-days* | 259 | 433 | 234 | 249 | 366 | 216 | 188 | 313 | 359 |

(2012-2016 from the reverse fold, 2017-2020 from the forward fold.)

## VIIRS fire-days in cell-days with no MODIS detection (2012-2020)

| month | VIIRS fire-days | of which MODIS zero | share | MODIS fire-days |
|---|---|---|---|---|
| 1 | 26.0 | 26.0 | 100% | 3.0 |
| 2 | 41.0 | 41.0 | 100% | 2.0 |
| 3 | 67.0 | 67.0 | 100% | 3.0 |
| 4 | 71.0 | 69.0 | 97% | 4.0 |
| 5 | 115.0 | 114.0 | 99% | 5.0 |
| 6 | 246.0 | 238.0 | 97% | 27.0 |
| 7 | 455.0 | 431.0 | 95% | 56.0 |
| 8 | 423.0 | 390.0 | 92% | 66.0 |
| 9 | 518.0 | 470.0 | 91% | 116.0 |
| 10 | 432.0 | 362.0 | 84% | 133.0 |
| 11 | 163.0 | 139.0 | 85% | 53.0 |
| 12 | 60.0 | 56.0 | 93% | 10.0 |
