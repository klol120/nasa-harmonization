# Forecasting decisions

Full implementation/state diagrams: [forecasting/docs/statecharts.md](forecasting/docs/statecharts.md).
Current measured status: [forecasting/docs/production-status.json](forecasting/docs/production-status.json).

## 2026-11-14 — Scope and release standard

* All new scientific inputs come from NASA services. Keep original bytes, URLs,
  retrieval timestamps, units, versions and checksums. Do not commit secrets/raw bulk data.
* Primary target remains satellite-detected vegetation-fire occurrence in the next
  24 hours. This does not predict spread, asset impact or all true ignitions.
* A deployable container/API and a scientifically validated production model are
  separate release requirements. Do not mark a synthetic or retrospective artifact
  production-approved. No live deployment is authorized by a readiness request alone.

## 2026-11-14 — Clouds and labels

* Acquire public NASA POWER cloud amount (total/day/night), sourced from SYN1DEG,
  as real cloud history. These coarse daily percentages are contextual data, not a
  substitute for clear/cloud classification at each MODIS/VIIRS overpass.
* Use NASA VNP14IMG full-mask/QA and matching geolocation for primary S-NPP
  observation evidence. VNP14A1 is a differently resolved sensitivity proxy.
* A no-detection cell-day is not automatically a true no-fire day. Keep unknown
  observation conditions separate; never erase a flagged positive and manufacture
  a negative. Do not infer clear satellite coverage from a low daily mean cloud amount.
* Protected NASA masks and environmental rasters currently reject unauthenticated
  access. No Earthdata token, username/password or netrc credential is configured.
  Implement authenticated acquisition without storing/logging credentials and continue
  independent work. Access cannot be fabricated or replaced with invented data.

## 2026-11-14 — Cleaning and split discipline

* Preserve all flag reasons; confirmed documented reviews cannot be downgraded.
  Recurrence is an uncertain review candidate fitted on 2012–2020 only.
* Reserve 2021–2022 for validation and 2023–2025 for final Lebanese testing, with
  boundary embargoes. Full raw-archive counts are label-quality bookkeeping, not fitting.
* Keep a full candidate rectangle rather than a fire-selected grid, but do not
  call it a national vegetation forecast grid before a verified boundary/fuel mask.

## 2026-11-14 — Models and forecasts

* Begin with smoothed seasonal frequencies and unweighted logistic regression.
  Fit preprocessing only on training data. Select model/threshold using validation.
  Do not select a filtering policy by comparing metrics on changed target populations.
* NASA POWER is historical weather; fitting it would be a retrospective prototype.
  It does not establish the performance of a model using issued GEOS forecasts.
* The inspected historical GEOS-CF air-quality collection lacks needed meteorology;
  do not substitute air-quality fields or analyses and call them forecast history.
* Production serving must fail closed when the artifact is synthetic, retrospective,
  unapproved, mismatched, missing required data or outside validated conditions.
  Readiness reports/statecharts must show incomplete stages explicitly.

## 2026-11-14 — Deployment implementation and verification

* Separate `/healthz` (process liveness) from `/readyz` (approved-model readiness).
  Refuse forecast service without an API key, passing release manifest, matching
  artifact checksum and a real archived-forecast model. Apply strict domain checks.
* Release checks require documented coverage/grid/feature/forecast/incident/calibration/
  sensor evidence, at least 200 positive test windows spanning at least two years,
  and improvement over the seasonal baseline on AP and Brier. These are minimum
  engineering/research gates, not a demonstrated emergency-service acceptance standard.
  Threshold/alert-cost review remains necessary before operational adoption.
* Decode GEOS units/timestamps from the actual sample. Derive 2m relative humidity
  from QV2M, pressure and T2M; record clipping of supersaturation. Require all forecast
  hours from one issue and independently supplied precipitation before daily aggregation.
  Do not fill missing rainfall or hours with zero.
* Match VNP14IMG with full VNP03IMG geolocation, not sparse fire-point coordinates.
  Current mask decoder outputs sampled-pixel evidence only. It cannot by itself
  authorize daily negatives without QA, a verified denominator and overpass completeness.
* Docker runs as UID 10001 with read-only filesystem, temporary storage, dropped
  capabilities and no new privileges in the smoke test. Model artifacts are to be
  mounted read-only. A production environment still needs TLS, access controls,
  monitoring, source refresh, rollback and operational validation.
* The first Docker build failed because the session proxy CA was not trusted inside
  the build. The successful build used the executor's public CA bundle as an optional
  BuildKit secret and kept TLS verification enabled; no session CA was baked into layers.

## 2026-11-14 — Newly added credential visibility

The user reported adding a key. A fresh shell still has no Earthdata credential,
and the live Cloud Environment status reports current observations with no configured
secret or runtime-variable bindings. Diagnose the setting location/application to this
running instance; do not claim successful authentication, print a credential, or ask
for it to be pasted into chat. Continue independent public-data/engineering work.

## 2026-11-14 — Forecast freshness and acquisition scale

* Withhold forecasts issued more than 24 hours before prediction by default; record
  and validate a different limit before changing it. Reject availability preceding
  issue time. This complements complete-hour and single-issue checks.
* The inspected CMR samples report roughly 0.49 MB for a VNP14IMG mask versus
  166.65 MB for its full VNP03IMG geolocation. Do not bulk-fetch the entire historical
  swath archive blindly. Evaluate server subsetting or a self-consistent gridded
  fire-mask target after authenticated sample inspection. Keep resolution/target
  definitions explicit rather than claiming a 750m-derived mask verifies 375m detection
  completeness. The data-budget decision must not silently change labels.

## 2026-11-14 — Authenticated NASA access and self-consistent labels

* The user supplied an Earthdata credential. An actual protected VNP14A1 science
  download succeeded. It is held outside the repository with restrictive permissions;
  never embed its value in code/configs/reports. Replace/revoke the shared token afterward.
* NASA CMR discovered 10,119 VNP14A1 daily files across h20v05/h21v05 for 2012–2025.
  Use restartable bounded concurrency and a disk reserve; preserve raw bytes/manifests.
* Build the first real research dataset using VNP14A1's own daily 1km fire/cloud
  classification (derived from VIIRS 750m bands). This is a product-specific detected
  occurrence target; it is not interchangeable with FIRMS' 375m detections. Keep FIRMS
  separately for documented non-target flags and comparison, not mixed-resolution zeros.
* The daily composite provides processed-pixel evidence, not continuous 24-hour
  observation or ground-truth no-fire evidence. Require a clear/processed eligible-area
  fraction, preserve unknown/cloud/unclassified outcomes and report conditional coverage.
* NASA FIRMS publicly serves `/content/geodata/world_countries.geojson`; use its
  Lebanon country-selection geometry with explicit provenance. It is an analysis mask,
  not a legal assertion about borders. This replaces the unverified rectangle for fitting.
* Use pre-target 2010 MCD12Q1 land-cover observations as a fixed ecological baseline,
  SRTM elevation, and antecedent rainfall as environmental features in the first model.
  Reprocessed versions and observed POWER weather mean this remains an explicitly
  retrospective reconstruction until issued-forecast/availability validation is complete.
  Do not invent a full NDVI history from one downloaded composite or fill it with constants.

## 2026-11-14 — Current target and honest research/production boundary

* NASA's VNP14A1 catalog states S-NPP science-data delivery ceased on 2026-11-02.
  Prepare NOAA-20 VJ114A1.002 for the current-target candidate rather than assuming
  an S-NPP model transfers unchanged. Its own data start in 2018; do not invent
  NOAA-20 observations in 2012. Reserve 2018–2020 training, 2021–2022 validation,
  2023–2025 testing for that candidate; retain the longer S-NPP research benchmark.
* Both fitted positive and negative classes must pass the same minimum daily
  processed eligible-area fraction. Known positives below it remain explicitly
  `positive_low_coverage`, never zeros. Report probabilities as coverage-conditioned
  research estimates until unconditional operational calibration is established.
* Quarantine a cell-window containing a fire outside the fixed vegetation eligibility
  mask as well as policy-excluded detections; do not silently manufacture a negative
  by dropping an unmatched heat source or land-cover-mismatched positive.
* Use a three-day lag for the seven-day antecedent rainfall feature, consistently
  in historical reconstruction and genuine future-window feature assembly. Real
  inference history uses its actual retrieval timestamp; never backdate publication.
* Read regional GEOS subsets with HTTPS byte ranges, preserve physical units and
  exact issue/valid filenames, and retain subset hashes plus immutable source URLs
  and remote metadata. The subset hash is not a claimed whole-global-source hash.
* Complete live forecast inputs do not create a multi-year issued-forecast backtest.
  A retrospective weather reconstruction must remain clearly labelled and cannot
  be approved as an operationally validated model just to satisfy a delivery date.

## 2026-11-14 — Product-version QA correction before fitting

Inspection of actual MCD12Q1.061 attributes and the NASA collection-6 user guide
confirmed QC is categorical (0 classified land, 2 classified water), not the old
collection-5 bit field. The adapter now accepts those exact strict-quality categories,
leaves backfilled/corrected/missing categories outside that tier, and has a regression
test preventing QC=8 from being accidentally accepted via low-bit masking. Rebuild
static masks/features after this correction; no real model had been fitted yet.
Reference: https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCD12_User_Guide_V6.pdf

## 2026-11-14 — Download transport and spatial representation

* Bulk transfers use per-worker reusable HTTPS connections after a live transfer
  check and a regression test that authorization is stripped on cross-host redirects.
  Concurrency remains bounded. Restarting workers preserves verified completed cache
  files; incomplete files are never presented as completed science downloads.
* Grid locations use an actual eligible in-country kilometre pixel nearest the cell's
  vegetation centroid, with original grid centres stored separately. Border-cell
  predictions represent the in-country vegetation portion, not neighboring territory.
  Exported risk polygons are clipped to the NASA-served analysis geometry.
* Retrospective artifacts explicitly identify their label product, coverage-conditioned
  scope and observed-weather validation. Live GEOS inputs carry the source-transfer
  warning; these are not operationally validated probabilities.

## 2026-11-14 — Primary real-data analysis policy, fixed before fitting

Use the strict filtering policy as the primary real-data analysis because the task
prioritizes vegetation fires over probable static/non-target or low-confidence heat
sources. Keep conservative filtering as a separately reported sensitivity analysis.
This choice is made before any real model performance has been computed; do not pick
between policies by comparing Brier scores on different eligible populations. The
older synthetic demonstration's conservative primary policy is unchanged. Recurring
vegetation burns may be lost under strict filtering, so report those exclusions and
avoid claiming the remaining labels are certainly clean.

## 2026-11-14 — Completed real models and held-out evidence

* Downloaded and decoded all 10,119 catalogued S-NPP and 5,825 NOAA-20 daily source
  tiles. Both actual retrospective training/evaluation jobs completed. The primary
  NOAA-20 model selected by validation Brier is strict-policy environmental logistic
  regression; boosting was eligible and compared but did not win that criterion.
* Keep the already-frozen model and validation-F1 threshold. On the reserved later
  NOAA-20 test, AP is 0.00909 versus seasonal 0.00410, but precision is only 1.31%
  and recall 9.64%. Do not turn modest ranking improvement into a production claim.
  Do not switch to another model because its test metric appears better.
* Export the exact split identities and add score-quantile reliability diagnostics
  without fitting a new calibrator or changing model selection. Tied scores remain
  together. The reviewed test is now a known benchmark: future development needs
  fresh locked confirmation data rather than reusing it as an untouched test.
* A complete actual GEOS forecast now supplies all 124 eligible cells. Research
  outputs must retain retrospective, coverage-selection and POWER-to-GEOS source
  transfer warnings. One actual issue/window does not supply a multi-year issued
  forecast backtest or validate future observation coverage.
* Preserve the retrospective/operational release boundary. The actual release record
  fails operational weather mode, historical availability, issued-forecast backtest,
  independent incident separation and calibration review. No operational model is
  approved or externally deployed. These are scientific evidence gaps, not an
  unresolved Earthdata authentication problem.
* Regional/global and deep-learning work is deferred; positive windows, ecological
  transfer evidence and operational evaluation are the limiting factors. No full
  NDVI series, authoritative facility/conflict catalogue, independent ground-truth
  incident set or transmission-line layer was fabricated. NASA-only scope limits
  the requested third-party causal event adjudication.

## 2026-11-14 — Delivery corrections and resource limits

* Reproduction now includes a reusable fixed-source environmental acquisition module
  and exact NASA source plan, validated against the real cache. Historical FIRMS/
  POWER acquisition no longer requires a soon-expiring optional GEOS snapshot;
  complete forecast collection has its own issue-aware module.
* Source-specific gridded training reads its actual grid/split/horizon configuration.
  The daily adapter explicitly rejects unsupported horizons rather than silently
  relabelling a daily composite. These corrections retain the configuration used by
  the already-completed actual fit; no performance-based retraining occurred.
* Country clipping can produce MultiPolygons; optional exposure screening handles
  them, with a focused regression test. Display rare-event map probabilities on an
  explicitly labelled scale extending at least to the validation threshold; this
  changes presentation, not predictions or threshold.
* The full final unit suite passed 49 tests. Real notebook 06 executed static source
  transformation, label checks, frozen-model evaluation/release rejection and the
  actual GEOS research map. Initial notebooks remain clearly separated synthetic
  mechanics or historical readiness snapshots.
* The updated locked container built successfully after disabling disposable uv
  cache retention in the image and removing only this task's superseded images/
  cache. Its latest container launch exceeded this small workspace's disk capacity
  under the runtime's VFS copying. Preserve all NASA raw files and model artifacts;
  remove disposable task-owned build resources and verify the latest service directly
  in the locked environment. Record the resource-blocked latest image smoke test
  separately from the earlier successful non-root/read-only container test. Do not
  claim the latest image was smoke-tested successfully. Recommend 12–16 GB free
  disk for full reproducibility including container creation.
