# External pretrained model adaptation

```mermaid
stateDiagram-v2
    [*] --> DiscoverPublishedModels
    DiscoverPublishedModels --> ReviewCheckpointLicenseAndInputs
    ReviewCheckpointLicenseAndInputs --> ExcludeFromRun: Non-NASA pretraining, task mismatch or unresolved license
    ReviewCheckpointLicenseAndInputs --> PinThreePrithviCheckpoints
    PinThreePrithviCheckpoints --> VerifyFullSHA256AndSize
    VerifyFullSHA256AndSize --> StrictEncoderStateLoad
    StrictEncoderStateLoad --> CachePreNormalizationTokens
```

```mermaid
stateDiagram-v2
    [*] --> NASA2017HLSCatalogue
    NASA2017HLSCatalogue --> OutcomeIndependentSceneOrdering
    OutcomeIndependentSceneOrdering --> NativeReflectanceAndFmaskCrops
    NativeReflectanceAndFmaskCrops --> RejectCrop: Cloud, shadow, snow, water, aerosol or invalid reflectance
    NativeReflectanceAndFmaskCrops --> RetainExactRawSubset: At least 95 percent good pixels
    RetainExactRawSubset --> PublishedBandNormalization
    PublishedBandNormalization --> FrozenTransformerBlocks
    FrozenTransformerBlocks --> CachedTokens
    RejectCrop --> TryNextScene
    TryNextScene --> NativeReflectanceAndFmaskCrops
    TryNextScene --> ExcludeCellRows: No qualifying image remains
```

Missing-image positives remain counted in the exclusion audit. Original fire
cloud/QA uncertainty and southern conflict exclusions remain in the upstream
versioned labels. No fire outcome is used to select an HLS scene.

```mermaid
stateDiagram-v2
    [*] --> CachedPretrainedTokens
    CachedPretrainedTokens --> FrozenLayerNorm
    CachedPretrainedTokens --> TrainablePretrainedLayerNorm
    FrozenLayerNorm --> PoolImageFeatures
    TrainablePretrainedLayerNorm --> PoolImageFeatures
    PoolImageFeatures --> JoinWeatherAndEnvironment
    JoinWeatherAndEnvironment --> TrainLebaneseHead2018To2020
    TrainLebaneseHead2018To2020 --> WeightedLoss
    WeightedLoss --> UpdateHeadAndAllowedLayerNorm
    UpdateHeadAndAllowedLayerNorm --> TrainLebaneseHead2018To2020
    TrainLebaneseHead2018To2020 --> Calibrate2021
    Calibrate2021 --> SelectOnValidation2022
    SelectOnValidation2022 --> FreezeHashesAndThresholds
    FreezeHashesAndThresholds --> KnownLaterYearDiagnostics
    KnownLaterYearDiagnostics --> ReportAllCandidates
    ReportAllCandidates --> ProductionBlocked: No fresh operational validation
```

The seasonal, weather/environment logistic and no-image MLP controls use the same
rows and split years. Test scores never reselect weights or thresholds. These
checkpoints do not initially predict fires: their Lebanese occurrence heads must
be trained. New production inference would also need current, timestamp-verified
HLS and an issued-weather backtest; existing API approval gates remain closed.

```mermaid
stateDiagram-v2
    [*] --> ActualIssuedNASAGEOS
    ActualIssuedNASAGEOS --> WeatherHistoryAndPastNDVI
    WeatherHistoryAndPastNDVI --> SharedTimestampAndShapeChecks
    SharedTimestampAndShapeChecks --> Withhold: Future, missing, stale or wrong-window input
    SharedTimestampAndShapeChecks --> ImageQualifiedCellCheck
    ImageQualifiedCellCheck --> Withhold: No retained valid HLS crop
    ImageQualifiedCellCheck --> HLSAndCheckpointAvailabilityCheck
    HLSAndCheckpointAvailabilityCheck --> Withhold: Missing or future source timestamps
    HLSAndCheckpointAvailabilityCheck --> SouthernConflictScope
    SouthernConflictScope --> Withhold: Excluded southern cell
    SouthernConflictScope --> LabelFreeModelPrediction
    LabelFreeModelPrediction --> CSVGeoJSONAndResearchMap
    CSVGeoJSONAndResearchMap --> ProductionGateClosed
```

The executed 16–17 November UTC example returns 84/124 estimates. All 32 southern
cells and missing HLS/NDVI cases are withheld, preserving overlapping reasons.
Outputs identify the selected external candidate, model hash, forecast/source
timestamps and old-landscape warning. This example does not replace the earlier
project selection or establish operational forecast performance.
