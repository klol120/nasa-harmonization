# Normalized input contracts (schema v1)

Use UTF-8 CSV, WGS84 EPSG:4326 degrees, UTC ISO-8601 timestamps with `Z` or explicit
UTC offset. Required columns are defined in `firecast.data.REQUIRED`; extra columns
are retained. `firecast fixture` creates complete examples of every table.
Raw provider files must remain immutable. `load_inputs` records path, bytes checksum
and row counts; source downloads additionally record URL and original download time.
An ingestion timestamp is not evidence that historical data was available in real time.

* `cells.csv`: one unique grid ID, region, centre lat/lon, vegetation fraction [0,1],
  elevation metres, slope degrees [0,90], aspect degrees, and static-layer publication
  `available_at`. Grid ID is `floor((lat+90)/step)_floor((lon+180)/step)`;
  boundary cells use the lower-inclusive, upper-exclusive rule. Use an authoritative
  Lebanon boundary to intersect a full grid, retaining eligible vegetated cells even
  if they have never had fire. No Lebanon-wide real boundary is bundled. The fixture
  supplies three Lebanese cells and two Cypriot cells, not full national coverage.
* `weather.csv`: one row per cell, prediction time and forecast issue. `issue_time`
  is issuance; `available_at` includes dissemination delay. `valid_start` and
  `valid_end` cover the exact prediction window. The adapter must aggregate a complete
  hourly forecast sequence: temperature/humidity/wind means, precipitation sum,
  eastward/northward wind components (m/s). Do not average wind directions as scalars.
  Units: Celsius, relative humidity %, rain mm; `rain7_mm` is an antecedent seven-day
  sum ending at `history_end`. `history_available_at` must precede prediction.
  The pipeline does not manufacture antecedent rainfall from future forecast periods.
  Only the most recent issue **available by prediction time** is selected. POWER can
  supply older historical antecedent values only after respecting its actual latency.
  In retrospective mode only the future-weather issue/availability constraint is
  relaxed; history and vegetation still require historical availability evidence.
* `environment.csv`: time-stamped NDVI [-1,1], observation and publication/availability
  times per cell. Most recent observed record available at prediction time is joined.
  Composites must be dated by publication after the complete composite interval.
  Resampling a coarse raster does not create fine-scale environmental measurements.
* `detections.csv`: original detection ID, position, acquisition UTC, MODIS/VIIRS,
  processing version, original sensor confidence, source type or `unknown`, flag level,
  reason and source. MODIS confidence <30 and VIIRS `l`/`low` are uncertain; type
  1/2/3 indicates a probable non-target source only when the original product supplies
  the documented FIRMS type convention. Do not invent VIIRS type values. `normalize_firms`
  preserves raw CSV and canonicalizes one declared product file; missing columns fail.
  Canonical identical detections are deduplicated within that normalization; duplicate
  normalized identities fail ingestion. Cross-product/overpass incident deduplication
  remains a required real-data review. Multiple hits in one window produce one target.
* `coverage.csv`: cell, interval [start,end), sensor, observable fraction [0,1]. Supply
  evidence from clear-land/swath quality data, not the list of fire detections.
  A negative requires one qualifying interval covering the whole horizon, by default
  fraction >=0.8. Partial intervals are conservatively left uncertain, not merged.
  This is an imperfect coverage proxy, not proof every fire was observable. At least
  one unexcluded detection can establish a positive without full coverage; evaluation
  therefore has selection bias that must be reported. Coverage is label quality only.
* `events.csv`: optional review records, with header even if empty. Event ID, point,
  UTC start/end, uncertainty radius km, confidence level, reason, source, reported_at.
  Spatial radius and time windows match detections for **historical label review**;
  reported-later events are never features. A match flags association for review and
  cannot prove the event caused the hot spot. Administrative centroids and broad
  event dates need wider, explicitly documented uncertainty, not precise attribution.

The two policies both quarantine an entire cell-window containing a confirmed
non-target detection. Conservative retains probable/uncertain positives; strict
quarantines them too. Missing coverage without a positive is `uncertain`.
Excluded and uncertain targets are null, never zero. Unflagged is not certified clean.
Recurrence creates uncertain candidates only: >=30 distinct active days at a rounded
0.001-degree position and detections on >=50% of days between first and last detection.
This retrospective review heuristic is not an industrial classifier. Its counts can
use the review archive; they never enter features. Freeze the review archive/version
when comparing experiments and review candidates against land cover/facilities.
Managed agricultural burning is included until a defensible target-specific flag is
supplied. There is no automatic distinction between agricultural and wildland fires.

Dataset version = input SHA-256 manifest + full config + package/code revision.
Save `git rev-parse HEAD` with externally distributed runs. Exported datasets retain
label status, detection counts, source times and policy-specific detection audits.
No negative sampling or class weighting is used: probabilities retain the supplied
eligible cell-window prevalence. Subsampling or weights would require prior correction
and independent calibration before interpreting probabilities.
