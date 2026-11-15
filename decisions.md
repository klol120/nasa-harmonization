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

## 2026-11-14 — Literature review and comparable metrics

* Review six primary fire-modeling studies, including global PoF, Mediterranean
  temporal models, western-US ignition models and a separately identified spread
  benchmark. Record tasks, sampling, split design, metric definitions and source
  versions in `forecasting/docs/literature-review.md`. Reading non-NASA research
  does not change the NASA-only predictor constraint.
* Add a reporting-only diagnostic script. Reuse the frozen global validation winner
  and verified splits; do not train, select, calibrate or change thresholds. Its
  ROC-AUC is 0.90230 on later global source-site dates, 0.87793 on held-out global
  panels, and 0.55173 on the repeated Lebanese fold. Prior average precision exactly
  reproduces. High ROC-AUC does not solve the poor alert precision/recall problem.
* Treat published case-control AUPRC and all-cell natural-prevalence AP as different
  evaluations. Mesogeos paper-v2 scores differ from its project-page leaderboard;
  retain both versions explicitly. Do not claim that protocol differences prove
  leakage or erase our genuine Lebanese performance deficit.
* Prioritize event/persistence audits, contiguous daily histories, NASA vegetation
  and soil-moisture proxies, and controlled XGBoost/temporal-model comparisons.
  These are proposed experiments, not completed improvements. Preserve existing
  conflict/cloud exclusions and freeze genuinely fresh confirmation before further
  development. No threshold tuning or renewed selection against viewed 2026 data.
* Account for composite completion, processing/version availability and actual
  release latency. SMAP soil moisture is not direct fuel moisture, and its normal
  mean latency is not a delivery guarantee. Storage expansion is needed before a
  substantial new multi-variable acquisition in this almost-full workspace.

## 2026-11-15 — Prioritize the Greek study and measure regional similarity

* Make Kondylatos et al. (2022), DOI 10.1029/2022GL099368, the main methodological
  reference. Inspect its supplement and pin released code to commit
  2b18bcf194284d56bd4e1774f7d5315db94cba34. Preserve the global baseline and
  global/region/Lebanon before-and-after comparisons requested earlier.
* Execute a development-only NASA comparison using 2018–2020 POWER and existing
  terrain/vegetation data. Weight actual weather points by their assigned eligible
  cells, not by unused ocean sample locations. Compare monthly temperature, rainfall,
  humidity and terrain. Greece has similar seasonal temperatures, but the sampled
  Greek panel has summer precipitation 105.83 mm versus 8.46 mm for our Lebanese
  grid, and mean sampled elevation 463 m versus 945 m. Do not call either sampled
  domain representative of every part of its country or assert climate equivalence.
* Four-panel standardized distances are exploratory and do not determine final
  training weights. Within-Greece matching needs broader Greek coverage and
  vegetation/fuel history. Do not select source regions from test fire outcomes.
* The existing Greek panel is a geographic holdout. A new Greek-trained model needs
  newly registered splits; it cannot inherit the old independent-geography claim.
  The audit reads no fire labels or test scores. Current frozen artifacts remain
  unchanged and their known 2026 outcomes cannot be fresh confirmation again.
* The supplement assumes historical weather represents available forecasts. Do not
  reproduce that assumption as operational validation. Preserve actual issue,
  availability and composite-end timestamps in a NASA adaptation. Keep the existing
  next-day detected-occurrence target and cloud/conflict exclusions.
* Distinguish the supplement's stated LSTM dense head (32/16) from the pinned code
  and hidden-size-64 experiment, which yields 64/32. Record variants explicitly.
  Prioritize a ten-day LSTM against matched trees; defer ConvLSTM until coherent
  spatial sequences and compute support a meaningful comparison. No new temporal
  model was trained during the review; no expected precision is promised.
* The authors' mixed-source archive needs at least 250 GB decompressed and would
  violate the requested NASA-only training provenance. Do not download it into a
  workspace with about 286 MB free. Reuse our NASA caches for the actual audit and
  document new-data/storage/confirmation prerequisites for later experiments.

## 2026-11-15 — Execute the Greek-inspired NASA temporal experiment

* Acquire actual NASA MOD13C2.061 monthly NDVI/quality/reliability and NASA POWER
  MERRA-2 root/surface wetness. The completed history has 110 monthly composites
  sampled at 9,411 cell locations and 1,293,732 soil-wetness point-days at 396 points.
  These coarse products are fitness/resource compromises, not exact substitutes
  for the Greek paper's 1 km vegetation and EDO moisture. Retain full selected raw
  arrays, original/subset hashes and URL/timestamp provenance; global containers
  are transient. Public modeled wetness has missing values; never zero-fill them.
* The CMG guide redefines QA bits 14–15 as spatial contribution. The initial audit
  caught an incorrect tiled-product interpretation before fitting. Correct it,
  require good clear land/reliability and sufficient contribution, and regression-
  test the actual bit pattern. Exclude climatology-filled reliability=4. Add NDVI
  age and a missing-prior-change indicator; never use future composites.
* Fit 10-day histories ending four days before target, plus historical current-day
  weather proxies/static environment. These are retrospective perfect-weather
  experiments. A declared three-day weather lag or sixteen-day NDVI lag does not
  establish historical release/version availability. Operational backtesting still
  requires actual issued meteorology and historically available land products.
* Match 163 of 326 Greek cells using development-only weather/terrain, without fire
  outcomes. Two sampled dates/month yielded zero positive training windows there;
  expand all Greek dates in 2018–2022 instead of selecting fire days. Obtain 1,819
  available daily sources; preserve seven missing catalogue days as uncertainty.
  The prepared Greek training set has 118,678 examples and only 67 positive windows.
* Keep source/global fitting in 2018–2020, separate 2021 calibration and 2022
  validation, with fourteen-day gaps. Common feature-qualified fitting populations
  have 379,751 global windows/5,605 positives and 109,567 Lebanese windows/197
  positives. Feature exclusions preserve their positive counts separately.
* Benchmark 45 source/Greek/local/transfer-stage candidates: seasonal, logistic,
  RF, XGBoost, true LSTM32/LSTM64, and matched weather-only linear/XGBoost controls.
  Neural stages continue weights with frozen parent scalers; tree/linear stages
  refit with a frozen parent score. No claim of continued tree weights. Class-
  weighted neural fitting requires separate natural-prevalence calibration.
* Use a CPU-only optional PyTorch/XGBoost environment. Source LSTM pretraining took
  307.68 seconds; the subsequent full comparison including cache reuse took 415.65
  seconds. Source-data/tuning hashes check cached weights. Fit/calibration sources,
  seed, runtime versions, model hashes and source-code hashes are retained. ConvLSTM
  is not justified by the current coarse spatial inputs and sparse incidents.
* Source validation selects `lstm64-global`; Lebanese overall validation selects
  `lstm64-lebanon`; transfer validation selects `logistic-global_greek_lebanon`.
  Freeze every candidate and threshold before new November label acquisition.
  Register 1/7 November 2026 beforehand; five geographic panels stay held out and
  Greece becomes a declared source region in regional arms. A fixed geographic
  router preserves the selected global model outside Lebanon and transfer inside.
* New November confirmation has 38 source-panel positive windows, 53 geographic-
  holdout positives, and zero Lebanese positives among 172 qualified examples.
  Local AP/recall cannot be established there. Missing local events are not evidence
  of useful detection. Keep weak global November scores and frozen thresholds.
* Add separately labelled known-year diagnostics without refitting or reselection.
  On 2023–2025, global LSTM AP is 0.17338 on designated source panels but only
  0.05939 on independent geographic panels. The neural global→Greek→Lebanon chain
  reaches Lebanese AP 0.01414 versus 0.00775 for local-only LSTM, but it did not win
  validation and is not promoted from known test results. On known 2026 data it
  detects 3/15 with 508 false alerts; the selected local model still misses 15/15.
  No production readiness or high precision is demonstrated.
* Complete a real future-input path using 72 NASA GEOS subsets for 16 November UTC,
  actual antecedent weather/wetness and MODIS availability records. The local
  research model returns 88 probabilities over 124 cells. Withhold all 32 southern
  scope cells and six missing-vegetation cases, with two overlapping reasons.
  Inputs contain no future fire label. CSV/GeoJSON/map outputs retain warnings,
  model hashes and timestamps; missing/future/wrong-window inputs suppress scores.
* Fit new work into limited disk by losslessly packing/verifying every remaining
  S-NPP and original NOAA-20 file, using memory-backed temporary MODIS reads and a
  persistent symlinked CPU software cache. Preserve archive/member checksums and
  restore commands. Do not describe packed original files as discarded data.
* Release stays false: no multi-year issued-forecast backtest, uncertain historical
  processing availability, limited independent incidents and poor practical local
  performance. Publish measured results, notebooks and all statecharts, not secrets
  or large raw/model archives in Git. Existing API production gates remain closed.

* Final engineering verification: full suite 88 passed with one existing Starlette
  deprecation warning; ten temporal tests rerun after final timestamp/scope guards.
  Notebook 10 executed real frozen-result reproduction and actual forecast-output
  inspection; all ten notebook schemas validated. Compilation, JSON, whitespace,
  frozen-artifact hashes and research-bundle member hashes passed. No fresh Docker
  build or remote GitHub CI result is claimed. Post-fit changes add reporting and
  safer label-free inference; frozen weights/calibrators/thresholds never change.

## 15 November 2026 — external pretrained checkpoints

* Interpret the new request as adapting external published weights, separately
  from our own previously fitted global/Greek models. Preserve NASA-only training
  and predictor provenance. Software/checkpoints may come from their authors'
  public hosts; this does not add another environmental data provider.
* Review actual Greek uncertainty-aware checkpoints, Mesogeos/Greek temporal
  implementations, ECMWF Probability-of-Fire and spread models. Their mixed data,
  unresolved checkpoint reuse rights or different task/input contracts prevent
  silently presenting them as compatible NASA-only occurrence forecasters.
* Select three distinct Apache-2.0 NASA-pretrained Prithvi checkpoints: EO1
  100M, EO2 Tiny TL and EO2 100M TL. Pin immutable revisions, complete file sizes
  and SHA256. The current Tiny and Tiny TL aliases resolve to identical weights
  and are counted once. These are self-supervised image encoders, not already
  trained fire-occurrence classifiers.
* Obtain NASA HLS Landsat L30 v2 COG crops and Fmask using outcome-independent
  2017 scenes. Use the recorded vegetation centroid, one 32x32 native 30m crop per
  cell. This 960m sample is a limited old landscape proxy within a roughly 10km
  forecast cell; do not imply complete cell coverage or current fuel condition.
* Require at least 95% clear valid pixels, excluding cirrus/cloud/adjacency,
  shadow, snow, water, fill and high aerosol. Retain native bands and QA, masks,
  observation/source/retrieval metadata and checksums. Residual invalid pixels
  are mean-filled under each checkpoint's original normalization. Missing-image
  rows preserve positive exclusion counts. Original label/cloud/conflict
  quarantines carry through unchanged.
* Stream large source checkpoint bytes to RAM and verify them before strict
  encoder loading. Retain exact cached pre-final-LayerNorm tokens and original
  final-normalization parameters, not complete source checkpoint files. New-image
  extraction must re-download the pinned source. This fits the small disk without
  deleting the original NASA science archives. Do not execute remote model code.
* Compare frozen-encoder heads and actual fine-tuning of the pretrained final
  LayerNorm scale/bias plus a new head. Earlier attention blocks stay frozen.
  This is limited encoder fine-tuning, not full-backbone training. Retain
  seasonal/weather/environment logistic and no-image MLP controls on identical
  image-qualified cohorts, with twelve fixed head epochs and recorded weight
  changes. Use 2018–2020 fit, 2021 calibration, 2022 validation and fourteen-day gaps.
* Freeze candidates and validation thresholds before known-year scoring. The
  2023–2025 and Jan–Oct 2026 Lebanese folds were already viewed; do not call them
  fresh independent confirmation or select from them. Modern pretraining weights
  were unavailable at historical issue times; EO2 Lebanese image exposure cannot
  be ruled out, and reprocessed HLS availability is unverified. Keep the
  retrospective-weather limitation and production approval false.
* Acquisition completed with 115/124 image-qualified cells, with no failed granule
  requests. Missing-image exclusions remove 32/197 fitting positives, 3/32
  validation positives and 20/133 known 2023–2025 positives. Report this changed
  population and score previous frozen references on exactly the same test rows;
  do not compare directly with their earlier all-qualified-cell scores.
* Ten new candidates were fitted. All three actual pretrained final-normalization
  tuning arms changed weights (L2 changes approximately 1.514, 0.754 and 1.423);
  frozen arms changed none. Neural head fitting took 137.43 seconds in total.
  The new comparison selects the EO2 100M TL frozen encoder plus Lebanese head,
  not its tuned-normalization arm. It has matched validation AP 0.002994, below
  the earlier local LSTM reference's 0.003072; do not replace project selection.
* On already-known 2023–2025 rows, selected external AP is 0.016956 versus matched
  old local LSTM 0.006683. Its threshold detects only 5/113 with 160 false alerts.
  Known 2026 has zero of 14 detected with 33 false alerts. Retain these failures.
  The nonselected normalization-tuned arm's slightly higher older-test AP does
  not cause promotion or a new threshold. No production skill is established.
* Cross-module delivery exposed __main__ class names in initial CLI serialization.
  Fix future CLI fitting to instantiate canonical module classes. Preserve original
  frozen file bytes/selection/results in a verified ZIP, canonicalize seven class
  references, verify complete deserialized object-state hashes unchanged, and
  record old/new artifact hashes in the selection receipt. No learned parameter,
  calibration, threshold or validation choice changes; re-score all tests to verify
  identical metrics. This is a packaging migration, not retraining.
* Reuse the actual issued GEOS forecast tensors for the 16–17 November UTC example.
  Shared inference now passes cell IDs without labels and separately checks HLS
  observation/retrieval and checkpoint retrieval timestamps. Missing/future source
  timestamps and missing-image cells withhold predictions. The new external arm
  produces 84 research estimates over 124 cells; all 32 southern-scope cells are
  withheld, with overlapping missing HLS/NDVI reasons preserved. Old 2017 HLS is
  explicitly flagged, never represented as current fuel imagery.
* Full suite: 93 passed and one existing Starlette warning. Fifteen focused checks
  passed for temporal/external contracts. Notebook 11 executed actual model loading,
  label-free prediction and AP reproduction. Production approval and deployment
  remain false; fresh container and remote CI checks were not run for this stage.

## 15 November 2026 — requested 2016–2017 evaluation

* Evaluate the existing 2018–2020-trained models without fitting, recalibrating,
  threshold changes or model selection. Earlier local S-NPP models already used
  2016–2017 and must not be called held-out references.
* NOAA-20 VJ114A1 labels do not cover these years. Use the already obtained NASA
  S-NPP VNP14A1.002 daily masks and original audited strict/conservative label
  tables; this is an explicit backward-time and cross-sensor diagnostic.
* The latest pretrained heads contain 2017 HLS tokens, which would introduce
  future-image information in 2016. Acquire separate 2015 NASA HLS crops and
  replace only image inputs, preserving encoders, head weights, scalers,
  calibrators and thresholds. Missing older images remain excluded.
* Acquire older NASA monthly NDVI and POWER modeled wetness; preserve the
  original weather and feature definitions. For overlapping source dates require
  identical values, retain the original copy, and audit overlap counts. Do not
  silently blend processing versions.
* Modern model weights and reprocessing were unavailable at historical issue
  times. Report retrospective transfer, not prospective operational forecast
  performance. Whole-year 2016/2017 outcomes never select a new model or threshold.
* Complete acquisition: 28 NDVI composites, 9,144 wetness point-days and 118/124
  qualifying 2015 HLS crops. Verify/deduplicate four NDVI months and 372 wetness
  point-days already present. Original image-domain intersection remains 115 cells.
* Actual earliest supervised fitting target is 5 January 2018. Apply the existing
  14-day embargo to exclude 21–31 December 2017 (1,364 raw cell-windows, 800 strict
  qualified examples, no positives). Retain those rows and exclusion masks rather
  than deleting them. An unscored intermediate was rebuilt for this gap; its
  superseded manifest is retained. Scored receipts prevent overwriting evaluated
  cohorts, including when a custom output directory is used.
* Score 14 frozen models in 72 year/policy/cohort combinations. Strict full-grid
  cohorts contain 39,260/90 positive windows in 2016 and 37,730/36 in 2017. Matched
  image cohorts contain 36,587/78 and 35,168/31; missing past NDVI removes two
  2017 positives and image-domain matching excludes another 12/5 positives.
* Selected external EO2 100M frozen-head AP is 0.010080 in 2016 and 0.003374 in
  2017, with no issued alerts at its original threshold: all 78/31 positives are
  missed, with no false alerts. Precision is not estimable with zero alerts;
  retain the metric zero convention only alongside its estimability flag.
  Local LSTM matched AP is 0.018303/0.003107, detecting 3/78 with 87 false alerts
  in 2016 and 0/31 with 73 false alerts in 2017. Other candidate scores are also
  retained, including higher-ranking nonselected Tiny variants; do not promote
  one after inspecting this older evaluation.
* Add explicit older-source discovery and registration for independent reproductions.
  Registrations pin already trained models before older outcomes are inspected;
  they cannot silently replace different existing snapshots. The committed run's
  protocol and original model files remain unchanged. Published HLS metadata corrects
  one legacy narrative year while retaining exact source dates and the cached
  extraction manifest hash; raw arrays and tokens are unchanged.
* Full suite: 98 passed, one existing Starlette warning. Twenty focused checks
  passed, including overlap refusal, image-only input substitution, preservation
  of uncertain positives, past-image bounds and immutable registrations/scored
  cohorts. Notebook 12 executed and reproduced the selected external model's AP
  and confusion counts without supplying labels as prediction inputs. No new
  training, calibration, threshold selection, Docker build or remote CI is claimed.
