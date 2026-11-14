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

## 2026-11-14 — User-directed global pretraining and repeated transfer benchmarks

* Supersede the earlier deferral of global training: the user now explicitly requests
  global models, Lebanon adaptation, multiple algorithms and neural-network options.
  Compare each global source model on held-out global and Lebanese observations,
  then evaluate its adapted versions on both domains to expose forgetting.
* Repeat development on calibration/validation years only. Existing 2023–2025
  Lebanese outcomes are already known; reserve 2026 through October as a new
  Lebanese confirmation set and freeze candidates before inspecting its outcomes.
  Global 2023–2025 data are newly reserved; entire selected sites also provide a
  geographic holdout. These observations are retrospective, not issued-forecast tests.
* Three CPU cores, no detected GPU and roughly 587 MB spare disk require bounded
  scientific subsetting. Use 24 predeclared 2° by 2° global panels, spanning the
  inhabited continents and broad latitude/climate regimes, with two independently
  date-seeded sampled days per month. Do not claim exhaustive planet-wide coverage,
  ecological matching or a uniform probability sample of all land.
* Retain exact unfiltered NASA source pixels, QA, raw environmental samples and
  provenance for these scientific subsets. Record original immutable source URLs,
  full-file hashes where full bytes are read, subset hashes and retrieval times.
  Temporary full source containers may be read and discarded after their selected
  raw scientific pixels are preserved; never delete the existing Lebanon archive.
* Fit before 2021, reserve 2021 for calibration, tune on 2022, and then freeze before
  global 2023–2025 / Lebanese 2026 confirmation. Main selection is Lebanese validation
  average precision, with Brier as a tie-breaker; report global retention separately.
  Keep natural class prevalence; use all qualified sampled cell-windows, not just
  positive sites, and never convert excluded/cloud-uncertain windows to negatives.
* Benchmark smoothed seasonality, logistic regression, random/extra forests,
  histogram boosting and three dense neural-network architectures. CPU-sized neural
  models are a justified experiment, not an assumption that DL must win. Distinguish
  actual neural weight continuation from calibration, ensembling and tree score
  transfer; do not call every adaptation method weight fine-tuning.

## 2026-11-14 — User-requested conflict exclusion after 7 October 2023

* The user requires southern Lebanon excluded from validation/testing from 7 October
  2023, or an adequate strike catalogue. Define the broad southern scope as South
  (LB6) and El Nabatieh (LB4), using CDR/OCHA COD administrative boundaries from HDX,
  with a 1 km boundary-uncertainty buffer. Exclude the entire 0.1° cell-window when
  its polygon intersects that region and its forecast window overlaps the period
  beginning 2023-10-07 00:00 UTC, with no assumed conflict end date.
* Acquire the actual OCHA/CDR GeoJSON resource and retain its archive, source API
  response, hash, exact ADM1 layer and CC BY-IGO attribution. The user's latest
  explicit request authorizes outside-NASA historical conflict-quality sources;
  all environmental/fire/weather predictors remain NASA-only. Do not use this
  retrospective review information as a model feature.
* Search found ACLED country/access/codebook documentation and official UN reporting.
  ACLED requires authorized access, aggregates some same-location/day events and has
  documented limitations; no exhaustive accessible strike-to-fire dataset has been
  established. Official reports document conflict outside the southern governorates
  too. The broad mask does not certify the rest of Lebanon conflict-free.
* Preserve every original label and exclusion reason/source in the audit, replace
  affected fitting/evaluation targets with null, and never convert an excluded fire
  to a negative. Apply the identical conflict mask to all new algorithm/adaptation
  comparisons and 2026 confirmation. Historical 2023–2025 results from the earlier
  unmasked run remain a separate superseded benchmark, not directly comparable.
* The chosen boundary layer is a historical quality-review geometry, not a claim of
  real-time 2023 availability or a legal border assertion. Inclusion in the excluded
  region does not assert that an individual fire was caused by conflict.

## 2026-11-14 — Actual global catalogue processing-version conflict

NASA's h22v10 catalogue contains two VJ114A1.002 versions for 2021-01-30,
processed in 2022 and 2023. Preserve both catalogue entries and the exact URLs;
select the latest processing timestamp deterministically within the same collection
and record every alternative in a version-choice audit. Never count both products
as independent observations. This is a retrospective reconstruction, so the later
processing version is not asserted to have existed at prediction time. A regression
test covers repeated identical entries and the later-version selection.

## 2026-11-14 — Rare-event optimizer variants fixed before benchmark fitting

Include naturally weighted and class-balanced linear/forest options. For neural
adaptation compare 5 epochs at 1e-4, 15 epochs at 1e-3, and 10 epochs at 3e-4 with
positive optimizer weight 10. The latter changes the optimizer's effective class
prior; always recalibrate it on the separate natural-prevalence 2021 Lebanese
calibration period, then assess calibration/skill on 2022 validation. This is not a
guarantee that calibration repairs all weighting effects. Do not oversample positive
sites or select sampled dates using fire outcomes. Keep all qualified sampled
windows and record actual family/candidate counts and selected parameters.

## 2026-11-14 — Lossless inactive-cache compaction and benchmark controls

* Full global source processing completed, and preparation produced 401,767 qualified
  global fitting windows / 5,769 positive windows before 2021, alongside the existing
  117,677 Lebanese windows / 202 positives. Calibration and selection remain separate.
* Preserve the previous model as a fixed reference evaluated on the identical new
  conflict-filtered population; do not attribute score changes caused by different
  exclusions to better algorithms. A small conservative-policy seasonal/logistic/
  boosting sensitivity suite is also fitted and frozen before primary confirmation
  is opened. Primary policy remains strict regardless of sensitivity results.
* Disk approached capacity while retaining all NASA source data. Losslessly pack only
  the inactive S-NPP raw cache into verified tar.gz batches. Verify every original
  file and provenance member hash after compression before removing its duplicate
  unpacked copy. Keep per-archive manifests and a tested exact restore command.
  Existing S-NPP scientific bytes are preserved; the active NOAA-20/global data and
  model artifacts are not deleted. Restore packed originals before rerunning the old
  S-NPP direct-file adapter.
* Export selected transfer artifacts with their global/local fit feature support,
  sampled-region/cell domain, label product, observed-weather validation source and
  time-dependent conflict-filtered evaluation scope. Research inference may retain
  a scope warning; strict production mode withholds outside reviewed conditions.
  The service still refuses retrospective models altogether.

## 2026-11-14 — Fixed recent-data refit and honest confirmation accounting

* The first benchmark completed 89 validation candidates, 58 frozen stage winners
  and nine predeclared conservative-policy controls. Source/local hyperparameters
  were chosen on their 2022 validation sets; 2021 was separate calibration data.
* Before manually reviewing numerical 2026 outcomes, fix one additional recipe from
  the immutable validation selection: the 64–32 neural global/local ensemble with
  75% local weight. Refit its unchanged source/local settings through 2024, calibrate
  on 2025 and compare matching global/local controls. Do not choose another recipe
  using confirmation scores. Newly acquire global 2026 sampled dates for independent
  global temporal/geographic confirmation.
* The original automatic benchmark had already scored the fixed Lebanese 2026 fold.
  Its later refit use is a repeated fixed-fold comparison, not a new independent test.
  That distinction is recorded in the protocol, frozen artifacts and final report.
* The actual refit uses 949,823 global windows / 12,903 positives and 260,804 Lebanese
  windows / 428 positives. Global and Lebanese 2025 calibration are separate. Compare
  both carried 2022 thresholds and the explicitly labelled 2025 calibration-F1 rule;
  neither rule is tuned on 2026. No numerical test result changes the selected model.
* Fixed seasonal, prior-probability and zero-probability diagnostics are reported
  without any new search or model selection. The selected transfer has no operational
  release approval; 15 eligible Lebanese 2026 positive windows and zero true positives
  at the frozen threshold are inadequate evidence for warning use.

## 2026-11-14 — Final QA audit and immutable-cache safety

* Audit all 5,825 original Lebanese NOAA-20 files, 4,608 original global scientific
  subsets, 479 available new global 2026 subsets and 608 Lebanese 2026 subsets for
  fire classes inconsistent with land QA. Two global native pixels in one Chilean
  2023 cell-window disagree with land QA; that window already had a null target in
  both policies. No fitted target, evaluation population or numerical result changes.
  Tighten the generic guard so an incompatible-QA fire always quarantines the window,
  even if the remaining clear-land fraction passes. Add a regression test preventing
  such a detection from silently becoming a negative.
* One of 480 requested global 2026 tile/date pairs is absent from the CMR inventory.
  Keep missing evidence uncertain; successful acquisition means all available
  selected sources were obtained, not that every requested observation existed.
* Shared static scientific arrays may use hard links, while mutable manifests and
  derived CSV metadata must be copied. A tested helper prevents regenerated target
  metadata from corrupting the source cache. Cached NASA JSON additionally checks
  that the recorded source URL matches the requested URL.
* Declare SciPy directly and require sklearn >=1.7 for neural sample weights. The
  lock preserves the fitted runtime library versions; only local project metadata
  is rebuilt. Preserve actual training-time source hashes; reporting-only edits and
  the zero-impact QA guard are not performance-selected retraining.
* The Lebanese forecast view withholds the same 32 post-conflict-scope cells, while
  the generic research artifact retains scope warnings. This is presentation/domain
  handling, not a learned strike feature or a claim that other cells are conflict-free.

## 2026-11-14 — Final measured outcome and delivery

* The fixed recent-data transfer has global temporal AP 0.15719 versus 0.15868 for
  its matching global source. Lebanese AP improves from zero-shot 0.000632 to
  0.003091, while the matching local-only control reaches 0.003372. Do not claim a
  transfer advantage over local fitting. Universal local calibration also worsens
  global probability calibration. Preserve the validation selection even though
  another model's confirmation result can look better.
* At the selected frozen threshold, all 15 eligible Lebanese positive windows are
  missed. A tiny Brier improvement over seasonal climatology is not practical
  alert readiness, and the zero-probability diagnostic scores slightly lower Brier.
  The real new release record is rejected; historical issued forecasts, independent
  incident/calibration review and adequate local confirmation size/span are absent.
* Notebooks 07 and 08 executed real source/subset inspection, conflict audit,
  immutable selection checks, frozen result reproduction and the country forecast
  with 32 withheld cells. The latest direct service smoke test with the actual
  refitted artifact records health 200 and readiness/forecast 503. No external
  model deployment occurred. A fresh global-extension Docker smoke test is not
  claimed under this workspace's storage constraint.
* Keep scientific outputs/data/models local and git-ignored. Publish code, notebooks,
  comparative metrics/figures, licences, statecharts and limitations on the existing
  user-requested feature branch. Provide a clearly named research-only model bundle;
  no secret, NASA raw archive or claim of production approval belongs in that bundle.
