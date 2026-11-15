# Frozen-model evaluation on Lebanese 2016–2017 data

**Evaluation only: no training, calibration, threshold changes or model selection. Production approval remains false.**

The current models were fitted on 2018–2020 labels, so 2016–2017 labels were not in their supervised fitting. Evaluating earlier years is a backward-time transfer diagnostic, not the later-year test required to establish forecasting skill. Modern weights and reprocessed inputs were not available at historical issue times.

## NASA sources and contamination checks

* Labels: existing NASA S-NPP VNP14A1.002 daily 1km fire masks, including cloud/unknown/coverage evidence and original FIRMS review. Current training labels use NOAA-20 VJ114A1.002, which does not cover 2016–2017. This is explicit cross-sensor evaluation, not a homogeneous NOAA-20 history.
* Earlier S-NPP-specific local models had already trained on 2016–2017 and are excluded from held-out comparisons. Current-model fitting tensor dates and artifact hashes are checked before preparation and scoring.
* The previous external heads contained 2017 HLS image inputs. Those would be future images for 2016, so separate QA-screened **2015 HLS** crops are encoded with the same pinned source weights. Only image inputs are substituted; all learned weights, scalers, calibrators and thresholds remain unchanged.
* 28 monthly MOD13C2.061 NDVI composites and 9,144 POWER modeled soil-wetness point-days were acquired. Four identical NDVI months and 372 identical soil point-days overlap the original caches; deduplicate with recorded checks, retaining original versions. Historical POWER weather already covers both years.
* Ten-day histories, past-composite NDVI availability and missing-feature exclusions remain unchanged. Target-day observed weather remains a retrospective proxy, not an issued forecast archive.
* Full daily 124-cell panels are retained. A fourteen-day embargo before the earliest fitting target, 5 January 2018, withholds 21–31 December 2017: 1,364 cell-windows before other exclusions. No eligible positives are lost to this embargo. Southern Lebanon is included: the requested post-7-October-2023 conflict quarantine does not apply to these years.
* Raw uncertain/excluded positives remain uncertain/excluded, not negatives. Strict/conservative label policies use the same frozen predictions and thresholds; their differing target populations are reported.

## Evaluated cohorts

| Year / label policy | Full feature-qualified windows | Full positive windows | Matched-image windows | Matched-image positives | Image-scope excluded positives |
|---|---:|---:|---:|---:|---:|
| 2016-strict | 39,260 | 90 | 36,587 | 78 | 12 |
| 2016-conservative | 39,553 | 110 | 36,792 | 91 | 19 |
| 2017-strict | 37,730 | 36 | 35,168 | 31 | 5 |
| 2017-conservative | 37,939 | 40 | 35,303 | 35 | 5 |

The matched image population intersects the original image-qualified training domain with valid 2015 crops: **115 cells**. All ten external-experiment candidates use this identical evaluation population. Earlier frozen references are scored both on it and on the full feature-qualified grid. Fire windows are not certified independent incidents.

## Strict-policy results on identical image-qualified rows

| Frozen model | 2016 AP | 2016 precision | 2016 recall | 2017 AP | 2017 precision | 2017 recall |
|---|---:|---:|---:|---:|---:|---:|
| seasonal | 0.003828 | 0.394% | 67.949% | 0.001317 | 0.140% | 61.290% |
| weather-logistic | 0.005706 | 0.708% | 14.103% | 0.003290 | 0.260% | 19.355% |
| environment-logistic | 0.010236 | 0.799% | 50.000% | 0.003618 | 0.216% | 35.484% |
| no-image-mlp | 0.009807 | 0.797% | 52.564% | 0.002797 | 0.267% | 45.161% |
| prithvi-v1-100m-frozen_encoder | 0.011570 | 1.869% | 2.564% | 0.004707 | 0.935% | 3.226% |
| prithvi-v1-100m-final_layernorm_tuning | 0.021710 | 1.042% | 1.282% | 0.004617 | 1.010% | 3.226% |
| prithvi-v2-tiny-tl-frozen_encoder | 0.026964 | 8.696% | 2.564% | 0.006431 | 0.000% | 0.000% |
| prithvi-v2-tiny-tl-final_layernorm_tuning | 0.027973 | 9.091% | 1.282% | 0.006450 | 0.000% | 0.000% |
| prithvi-v2-100m-tl-frozen_encoder | 0.010080 | no alerts | 0.000% | 0.003374 | no alerts | 0.000% |
| prithvi-v2-100m-tl-final_layernorm_tuning | 0.009645 | no alerts | 0.000% | 0.003701 | no alerts | 0.000% |
| lstm64-global | 0.003228 | 0.308% | 17.949% | 0.011016 | 0.391% | 38.710% |
| lstm64-lebanon | 0.018303 | 3.333% | 3.846% | 0.003107 | 0.000% | 0.000% |
| logistic-global_greek_lebanon | 0.010459 | 1.913% | 8.974% | 0.003962 | 0.745% | 12.903% |
| lstm64-global_greek_lebanon | 0.008034 | 0.814% | 6.410% | 0.002916 | 0.585% | 19.355% |

AP is average precision, not accuracy. Every threshold was fixed on the original 2022 validation; none was optimized on older outcomes. When no alerts are issued, precision is not estimable; the JSON retains a zero convention with precision_estimable=false.

## Filtering-policy sensitivity

| Model | Year / policy | AP | TN / FP / FN / TP | Brier |
|---|---|---:|---|---:|
| prithvi-v2-100m-tl-frozen_encoder | 2016 / strict | 0.010080 | [36509, 0, 78, 0] | 0.002120 |
| prithvi-v2-100m-tl-frozen_encoder | 2016 / conservative | 0.010658 | [36701, 0, 91, 0] | 0.002459 |
| prithvi-v2-100m-tl-frozen_encoder | 2017 / strict | 0.003374 | [35137, 0, 31, 0] | 0.000884 |
| prithvi-v2-100m-tl-frozen_encoder | 2017 / conservative | 0.004521 | [35268, 0, 35, 0] | 0.000992 |
| lstm64-lebanon | 2016 / strict | 0.018303 | [36422, 87, 75, 3] | 0.002117 |
| lstm64-lebanon | 2016 / conservative | 0.020853 | [36613, 88, 87, 4] | 0.002453 |
| lstm64-lebanon | 2017 / strict | 0.003107 | [35064, 73, 31, 0] | 0.000890 |
| lstm64-lebanon | 2017 / conservative | 0.003670 | [35194, 74, 35, 0] | 0.000998 |

## Earlier frozen references over the full grid

| Reference | 2016 strict AP | 2017 strict AP |
|---|---:|---:|
| lstm64-global | 0.003177 | 0.006191 |
| lstm64-lebanon | 0.015565 | 0.003310 |
| logistic-global_greek_lebanon | 0.011264 | 0.003168 |
| lstm64-global_greek_lebanon | 0.007648 | 0.003702 |

## Interpretation

The external candidate selected before this experiment remains `prithvi-v2-100m-tl-frozen_encoder`. The earlier project primary is also unchanged. Older scores do not select a new model, normalization strategy or threshold.

For the selected external candidate in 2016, the strict matched cohort contains 36,587 observations and 78 positive windows: **0 detected, 78 missed, 0 false alerts**, AP 0.010080.
For the selected external candidate in 2017, the strict matched cohort contains 35,168 observations and 31 positive windows: **0 detected, 31 missed, 0 false alerts**, AP 0.003374.

Differences from 2023–2026 scores can reflect sensor, image age, fire prevalence, weather regime and observable-population changes. They do not by themselves demonstrate improvement, explain the cause of newer failures or validate production. The 2015 images sample only 960m squares inside roughly 10km cells. EO2 unsupervised image exposure cannot be ruled out; modern pretraining and reprocessing availability remain retrospective limitations. Label adjudication also uses historical review and later recurring-hotspot evidence.

Full precision/recall/F1, confusion matrices, Brier scores, calibration, ROC-AUC and seasonal breakdowns are in [JSON](older-evaluation-results.json); [CSV](older-evaluation-results.csv) contains all candidates/cohorts. See [statecharts](older-evaluation-statecharts.md), [setup](../README.md#older-year-evaluation-20162017) and notebook 12.
