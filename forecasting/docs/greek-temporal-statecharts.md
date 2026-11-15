# Greek-inspired temporal pipeline statecharts

These describe the implemented research pipeline. Every production release remains
unapproved. ConvLSTM is a deferred experiment, not a trained model.

## NASA extraction, exploration, transformation and loading

```mermaid
stateDiagram-v2
    [*] --> SourceConfiguration
    SourceConfiguration --> CachedNASAInputs
    CachedNASAInputs --> DailyGreekFireMasks: VJ114A1.002, 2018–2022
    CachedNASAInputs --> DailyWeatherAndWetness: POWER meteorology and MERRA2 GWET
    CachedNASAInputs --> MonthlyVegetation: MOD13C2.061 NDVI and raw QA
    CachedNASAInputs --> StaticEnvironment: MCD12Q1 and SRTM
    DailyGreekFireMasks --> PreserveSourceEvidence
    DailyWeatherAndWetness --> PreserveSourceEvidence
    MonthlyVegetation --> PreserveSourceEvidence
    StaticEnvironment --> PreserveSourceEvidence
    PreserveSourceEvidence --> ValidateSchemasAndUnits: URL, retrieval time, version and hashes
    ValidateSchemasAndUnits --> DevelopmentRegionMatching
    DevelopmentRegionMatching --> SharedGrid
    SharedGrid --> TemporalFeatures
    TemporalFeatures --> VersionedTensorsAndAudits
```

The Greek training panel initially had zero positives with two sampled days/month.
Daily collection expanded all dates, not just fire days. Environment-only matching
retains 163/326 Greek cells using 2018–2020 weather/terrain; it never uses test fires.
Global fire-label dates remain sampled. Exact selected raw arrays and QA are
retained; original complete MODIS containers are transient with recorded hashes.
Older full daily fire files are losslessly packed with verified restoration.

## Labels, exclusions and feature availability

```mermaid
stateDiagram-v2
    [*] --> NativePixelQA
    NativePixelQA --> UnknownLabel: Missing catalogue, cloud or unknown fire
    NativePixelQA --> NonTargetReview: Fire outside vegetation or compatible land QA
    NonTargetReview --> ExcludedWindow
    NativePixelQA --> AggregateEligibleArea
    AggregateEligibleArea --> UnknownLabel: Less than 80 percent processed
    AggregateEligibleArea --> ConfidencePolicy
    ConfidencePolicy --> UnknownLabel: Low-confidence-only fire under strict policy
    ConfidencePolicy --> DetectedOccurrenceOrNoDetection
    DetectedOccurrenceOrNoDetection --> ConflictScope
    ConflictScope --> ExcludedWindow: Southern scope overlapping 2023-10-07 onward
    ConflictScope --> PastOnlyFeatures
    PastOnlyFeatures --> ExcludedFeatureRow: Missing daily history or valid past NDVI
    PastOnlyFeatures --> EligibleTensor
    ExcludedWindow --> PreserveOriginalLabelAndReason
    UnknownLabel --> PreserveOriginalLabelAndReason
    ExcludedFeatureRow --> PreserveOriginalLabelAndReason
```

An excluded positive is never relabelled negative. MODIS CMG QA bits 14–15 encode
spatial contribution, not tiled-product snow/shadow. Reject unreliable/climatology-
filled vegetation, enforce composite completion plus a declared lag, and retain
NDVI age/missing-change indicators. Ten-day weather/wetness histories end four days
before target day. Historical target-day weather remains an explicitly retrospective
perfect-weather proxy; historical release/version availability is not proved.

## Fitting and genuine neural continuation

```mermaid
stateDiagram-v2
    [*] --> Fit2018Through2020
    Fit2018Through2020 --> GlobalSource
    Fit2018Through2020 --> MatchedGreekSource
    Fit2018Through2020 --> LebanonOnlyControl
    GlobalSource --> GreekAdaptation
    MatchedGreekSource --> LebanonAdaptation
    GreekAdaptation --> LebanonAdaptation
    GlobalSource --> NaturalPrevalenceCalibration2021
    MatchedGreekSource --> NaturalPrevalenceCalibration2021
    LebanonOnlyControl --> NaturalPrevalenceCalibration2021
    LebanonAdaptation --> NaturalPrevalenceCalibration2021
    NaturalPrevalenceCalibration2021 --> Validation2022
    Validation2022 --> FreezeAll45CandidatesAndThresholds
    FreezeAll45CandidatesAndThresholds --> NewNovemberLabels
    NewNovemberLabels --> ImmutableConfirmationScores
    ImmutableConfirmationScores --> KnownLaterYearDiagnostics: Separate previously viewed benchmark
    KnownLaterYearDiagnostics --> ResearchReleaseAssessment
```

Fourteen-day gaps separate fitting/calibration/validation. All input scalers fit
training only. Seasonal/logistic/RF/XGBoost/LSTM32/LSTM64 models use identical
feature-qualified rows; weather-only logistic/XGBoost controls remove vegetation,
terrain and wetness inputs. Repeated search on only 32 Lebanese validation positives
is unstable. Tree/logistic adaptation adds the frozen parent score and refits local
weights; it does not continue tree weights. Neural adaptation actually continues
weights and freezes the parent's feature scalers.

## LSTM computation

```mermaid
stateDiagram-v2
    [*] --> TenDailyVectors
    TenDailyVectors --> TrainingOnlyStandardization
    TrainingOnlyStandardization --> LayerNormalization
    LayerNormalization --> LSTMMemory
    LSTMMemory --> InputForgetAndOutputGates
    InputForgetAndOutputGates --> FinalHiddenState
    FinalHiddenState --> JoinCurrentWeatherAndEnvironment
    JoinCurrentWeatherAndEnvironment --> DenseReLUAndDropout
    DenseReLUAndDropout --> FireLogit
    FireLogit --> WeightedTrainingLoss: Fit data only
    WeightedTrainingLoss --> AdamAndGradientClipping
    AdamAndGradientClipping --> LSTMMemory: Next training batch
    FireLogit --> SigmoidCalibration: Separate 2021 examples
    SigmoidCalibration --> Probability
```

Inputs include modeled root/surface wetness and historical weather. Current weather
proxies, terrain/season/location, past NDVI, age and change indicator join the final
hidden state. Class weighting changes the fitting objective; calibration does not
guarantee reliable probabilities under geographic or weather-source transfer.

## Actual forecast inputs and research inference

```mermaid
stateDiagram-v2
    [*] --> IssuedNASAGEOS
    IssuedNASAGEOS --> Complete24HourWindow: Retain issue, valid and retrieval times
    Complete24HourWindow --> AvailableNASAHistoryAndVegetation
    AvailableNASAHistoryAndVegetation --> ValidateFeatureContractAndTimestamps
    ValidateFeatureContractAndTimestamps --> Withhold: Missing, future, stale or wrong window
    ValidateFeatureContractAndTimestamps --> ConflictScopeCheck
    ConflictScopeCheck --> Withhold: Southern cells outside evaluated scope
    ConflictScopeCheck --> ResearchPrediction
    ResearchPrediction --> CSVGeoJSONAndMap: Model hash, timestamps and limitations
    CSVGeoJSONAndMap --> ProductionGate
    ProductionGate --> RefuseProduction: No issued-weather backtest or sufficient confirmation
```

The optional fixed regional router keeps selected global weights outside Lebanon
and selected transfer weights inside it. It is explicit routing, not a newly fitted
global improvement. Actual future inputs demonstrate engineering only: neither that
map nor the two November dates validate operational warning performance.
