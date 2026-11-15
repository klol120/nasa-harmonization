# Older-year evaluation statecharts

This evaluates frozen post-2018 models on older, cross-sensor observations. It is
not retraining, model selection or a simulation of a model deployed in 2016.

```mermaid
stateDiagram-v2
    [*] --> RegisterYearsAndFrozenHashes
    RegisterYearsAndFrozenHashes --> CheckActualFittingDates
    CheckActualFittingDates --> RejectContaminatedReference: Earlier S-NPP model already trained on 2016 or 2017
    CheckActualFittingDates --> ExistingSNPPDailyLabels
    ExistingSNPPDailyLabels --> StrictAndConservativePolicies
    StrictAndConservativePolicies --> QuarantineUncertainLabels: Cloud, unknown fire, low coverage or non-target flags
    StrictAndConservativePolicies --> QualifiedCellDays
    QualifiedCellDays --> RebuildOriginalWeatherFeatures
    RebuildOriginalWeatherFeatures --> PastOnlyNDVIAndWetness
    PastOnlyNDVIAndWetness --> FeatureQualifiedRows
    PastOnlyNDVIAndWetness --> PreserveExcludedPositiveCounts: Missing past history or valid vegetation
    FeatureQualifiedRows --> FourteenDayEmbargo
    FourteenDayEmbargo --> FullGridReferenceEvaluation
```

S-NPP VNP14A1.002 replaces unavailable NOAA-20 labels for these years. >=80%
processed eligible area remains conditional daily observation evidence, not proof
of continuous fire detectability. The original raw data and per-policy uncertain
labels remain intact. Southern cells are included before the 2023 conflict cutoff.
The embargo withholds 21–31 December 2017 before the earliest 5 January 2018 fit.

```mermaid
stateDiagram-v2
    [*] --> AuditImageObservationDates
    AuditImageObservationDates --> RejectFutureImageInput: Existing 2017 imagery cannot evaluate 2016
    RejectFutureImageInput --> Acquire2015NASAHLS
    Acquire2015NASAHLS --> ScreenNativeReflectanceAndFmask
    ScreenNativeReflectanceAndFmask --> MissingImageScope: No qualifying crop
    ScreenNativeReflectanceAndFmask --> VerifyPinnedPretrainedWeights
    VerifyPinnedPretrainedWeights --> Encode2015Crops
    Encode2015Crops --> SubstituteImageInputsOnly
    SubstituteImageInputsOnly --> PreserveHeadScalersCalibrationAndThreshold
    PreserveHeadScalersCalibrationAndThreshold --> MatchedImageCohort
    MatchedImageCohort --> ScoreAllRetainedCandidates
```

Input substitution uses separate model views and leaves original artifacts
unchanged. It is not fine-tuning. The 2015 and original token archives must have
identical pretrained final-normalization parameters/checkpoint identities. Weather
and environmental inputs keep their original feature definitions and units.

```mermaid
stateDiagram-v2
    [*] --> FrozenPredictionsWithoutLabels
    FrozenPredictionsWithoutLabels --> CompareWith2016Labels
    FrozenPredictionsWithoutLabels --> CompareWith2017Labels
    CompareWith2016Labels --> StrictAndConservativeMetrics
    CompareWith2017Labels --> StrictAndConservativeMetrics
    StrictAndConservativeMetrics --> APPrecisionRecallF1BrierAndCalibration
    APPrecisionRecallF1BrierAndCalibration --> YearSeasonAndCohortReports
    YearSeasonAndCohortReports --> VerifyOriginalArtifactHashes
    VerifyOriginalArtifactHashes --> RetainOriginalSelections
    RetainOriginalSelections --> ProductionStillBlocked
```

Modern weights, retrospective image processing and observed-weather proxies
prevent a historical operational-as-of claim. Sensor/fire prevalence and image-age
changes can affect scores. Counts describe positive cell-windows, not certified
independent incidents. Results do not select a new model or threshold.
