> Historical stage snapshot. Superseded for current run status by [actual results](current-results.md) and [production status](production-status.json). Earthdata access and real retrospective training now succeeded.

# Real-data preparation and statecharts

This stage uses the downloaded NASA observations. It is not another synthetic
training run and it does not manufacture real-data evaluation results.

From `forecasting/`, run:

```sh
uv run python -m firecast.real --data data/nasa-lebanon --config configs/real-preparation.json --out outputs/real-preparation
uv run python -m firecast.statecharts --readiness outputs/real-preparation/readiness.json --out docs/statecharts.md
uv run python -m firecast.earthdata --out data/earthdata-plan
uv run pytest -q
```

The real preparation command emits its own `statecharts.md`. The published
[`statecharts.md`](statecharts.md) contains eight diagrams covering acquisition,
cleaning, policy exclusions, labels, feature availability, models and evaluation/
inference. It distinguishes implemented code from blocked real-data stages.

## Actual transformations

`real.py` preserves source files and creates a compressed detection audit with each
NASA type, platform, version, confidence, reason and policy action. Original documented
review flags retain their severity and provenance; unknown reviews without evidence
are rejected. Volcano/static/offshore source types are **probable**, not independently
confirmed facility classifications. MODIS confidence below 30 and VIIRS low confidence
are uncertain. Invalid/unrecognized metadata quarantines affected windows in both
policies. All reasons are appended rather than replacing one another.

Recurrence uses 0.01° review bins with at least 30 active days in at least three years,
fitted on 2012–2020 only. Those bins nominate review candidates, not industrial truth.
The rule is frozen before validation/test. This is a deliberately simple uncertainty
heuristic, not a learned non-target classifier. The generic normalized-input pipeline
also now fits its separate fine-location recurrence heuristic before its training
cutoff, rather than across validation/test. Neither uses recurrence as an inference
feature. Incident/conflict cause is not inferred. The Beirut spatial-temporal match
remains a review field and is not an automatic exclusion.

The candidate grid covers the configured rectangle using 0.1° cells, including cells
without any recorded fire. It is **not** a verified Lebanon boundary or vegetation
mask. This avoids silently using a fire-selected grid, but includes neighboring/sea
cells until a mask is acquired. Country membership of positive detections follows the
NASA country files; no national probability forecast is issued from this rectangle.

Daily UTC windows are half-open. The real adapter currently supports 24 hours only
and rejects other horizons; the generic normalized pipeline supports supplied
horizon-specific aggregates. S-NPP is the primary label platform, with other sensors
kept for review/sensitivity. Any policy-excluded detection, including a different
platform's detection, quarantines the entire associated cell-window. Removing a
flagged positive never turns it into a negative. No-detection windows remain unknown
until compatible observability evidence exists. Coarse weather-point assignments
record geographic distance and reuse the original weather table; no historical
availability or fine-scale meteorology is invented.

2012–2020, 2021–2022 and 2023–2025 are assigned train/validation/test reservations;
seven-day boundary embargo windows remain separate. A training window must end
strictly before the lower embargo boundary. Quality bookkeeping counts test labels
but no model, preprocessing, recurrence rule or threshold fits on test data.
No separate incident IDs exist yet; long-lived incidents still require review.

## NASA environmental discovery and access

`earthdata.py` obtains exact collection IDs and sample granule URLs from NASA CMR,
not guessed file names. The query spans Lebanon's bounding rectangle and a short
2019 sample interval; at most eight granules per product are listed. It found:

* VNP14IMG.002: 375 m swath fire mask and algorithm QA; full swath geolocation must
  be acquired/matched (sparse fire-point coordinates are insufficient).
* VNP14A1.002: daily 1 km grid derived from 750 m bands; a sensitivity proxy, not
  interchangeable with 375 m target completeness.
* MCD12Q1.061: annual land cover and QA.
* MOD13Q1.061: 16-day NDVI/EVI and QA.
* SRTMGL1.003: elevation tiles for slope/aspect derivation.

These are **metadata discoveries**, not downloaded rasters or complete history.
Unauthenticated HEAD requests to the exact protected sample URLs returned HTTP 403
for all five products. No Earthdata token is configured. Authenticated access has
not been exercised, so authentication success is unverified.

The optional sample downloader accepts `EARTHDATA_TOKEN` from the environment only,
uses NASA HTTPS URLs, strips authorization on cross-host redirects, rejects login
HTML by checking science-file/container signatures, and saves checksummed provenance.
Configure credentials through a secure environment mechanism; never add them to
configs, notebooks, git, or chat. Once configured, the explicit sample command is:

```sh
uv run python -m firecast.earthdata --out data/earthdata-plan --download-samples
```

That downloads at most one candidate granule per product, not full history. Check
actual region overlap, geolocation, QA, units and processing metadata before bulk
acquisition. CMR catalog updates and reprocessed product dates do not prove that
those versions were available at a historical prediction time. Original-version
availability or an explicitly retrospective reconstruction remains necessary.

`environment.py` provides fixture-tested array transformations: MOD13Q1 scaling and
quality rejection; quality-qualified IGBP vegetation fractions; projected DEM slope
and downslope aspect; and instantaneous fire-mask observable-land fractions. These
are **not** a validated real-raster ingestion/reprojection pipeline. The fire-mask
codes follow the NASA VNP14IMG filespec; an instantaneous clear pixel does not
establish continuous daily observability or absence of fire. Browse imagery is never
used as a scientific mask. Flat terrain has undefined aspect, not a made-up direction.

NASA documentation:

* https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14IMG
* https://cmr.earthdata.nasa.gov/search/collections.json?short_name=VNP14IMG&version=002
* https://data.nasa.gov/dataset/viirs-npp-thermal-anomalies-and-fire-daily-l3-global-1km-sin-grid-v002-af393

## Forecast-history investigation

GEOS-CF v1 lists forecast years starting in 2019. However, the inspected
`2020/M08/D03/H12` issue directory contained the surface air-quality collection
`aqc_tavg_1hr_g1440x721_v1`, and the matching OPeNDAP schema exposes NO2, CO, O3,
PM2.5 and SO2, not the required temperature/humidity/precipitation/wind fields.
This checked route does not solve meteorological forecast-history access. That is
not proof no suitable NASA archive exists elsewhere. GEOS-FP's checked public
forecast directory remains recent. POWER remains explicitly historical weather.
No air-quality replay or assimilation fields were relabelled as forecasts.

Evidence URLs:

* https://portal.nccs.nasa.gov/datashare/gmao/geos-cf/v1/forecast/Y2020/M08/D03/H12/
* https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/fcast/aqc_tavg_1hr_g1440x721_v1.latest.dds

## Training gate

All non-synthetic calls to `train_experiments` now require an explicit passing
`real_data_readiness` report. The current report is false: there are no verified
negative labels, no national/vegetation mask, no historically available environmental
features and no complete multi-year forecast meteorology. The training gate fails
before fitting a model. Readiness flags are scientific checks on trusted inputs, not
a security mechanism against someone intentionally falsifying a configuration.

The existing fixture still demonstrates smoothed seasonal risk, logistic regression,
optional tree-model eligibility, train-only preprocessing, validation-only model/
threshold selection, later testing, calibration diagnostics and inference exports.
There are no new real-data model metrics. Positive-window counts are not independent
incident counts. Only after the missing evidence is integrated should training run
and then the reserved test period be evaluated.

## Verification of this stage

The full test suite passed: **31 tests**. The fourth notebook was schema-validated
and executed against the real downloaded detections, generating the readiness report
and eight Mermaid charts. Python compilation and `git diff --check` passed. New
numerical environmental functions were tested on small array fixtures only. The
Earthdata authenticated download path has not run because no token is configured.
The real-data model fit/test stages have not run. This branch remains local.
