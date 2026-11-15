# NASA source ledger: actual acquisition, 14–15 November 2026

The external-checkpoint experiment additionally acquired NASA HLS Landsat L30 v2
six-band 30m reflectance/Fmask crops observed June–October 2017, for 115/124
Lebanese grid cells. Each crop is a native 32x32 window, not full-cell coverage.
CMR `C2021957657-LPCLOUD` supplies discovery and protected NASA LP DAAC COGs supply
the pixels. Exact crops, QA, windows, source URLs, observation/retrieval metadata
and SHA256 are retained. HLS follows NASA open Earth-science data policy; Earthdata
authentication is required. Initial CMR-query retrieval time was not captured;
its file timestamp is explicitly retained as weaker evidence. Pixel retrieval
times are recorded directly. Reprocessed acquisition dates do not establish
historical dissemination availability.

Three externally hosted IBM/NASA Prithvi checkpoints use NASA HLS pretraining;
their Apache-2.0 licenses, pinned revisions/full-byte hashes, task/feature checks,
and rejected alternatives are documented in [the pretrained-source review](pretrained-sources.md).
Checkpoints are software/model artifacts, not an added non-NASA predictor source.
They were verified in RAM; full files are not cached. Cached tokens and final
normalization parameters are retained with provenance. These modern image encoders
are not historical fire forecasts and may overlap Lebanese imagery in EO2 pretraining.

The Greek-inspired temporal extension adds the following actual NASA acquisitions.
Its raw subset and API manifests carry exact URLs, versions, download timestamps
and hashes; totals do not count retained full source containers that were transient.

| Added source | NASA reference | Obtained coverage | Access, units and limitations |
|---|---|---|---|
| MODIS monthly vegetation | [MOD13C2.061](https://doi.org/10.5067/MODIS/MOD13C2.061), [C6.1 guide](https://modis-land.gsfc.nasa.gov/pdf/MOD13_User_Guide_V61.pdf) | 110 monthly composites, September 2017–October 2026, selected raw NDVI/QA/reliability at 9,411 cell samples; 0.05° CMG | Earthdata token. NDVI scale 0.0001; CMG bits 14–15 describe spatial contribution, not tiled-product snow/shadow. Reliability=4 uses historical filling and is excluded. Composite/reprocessing availability is not proved by a nominal date. |
| Daily soil wetness | [NASA POWER hydrology sources](https://power.larc.nasa.gov/docs/methodology/data/sources_hydrology/), [GMAO MERRA-2 units](https://gmao.gsfc.nasa.gov/gmao-products/merra-2/faq_merra-2/) | 1,293,732 point-days at 396 coarse-grid sampling points, December 2017–10 November 2026; plus 516 recent Lebanese point-days for the future-input demonstration | Public POWER API, GWETROOT/GWETTOP dimensionless modeled relative wetness. Standard MERRA-2 meteorological grid, roughly 0.5° × 0.625°. Not SMAP retrievals, volumetric moisture or direct fuel moisture. Missing values remain missing; point samples are not independent weather grids. |
| Daily Greek fire/coverage | [VJ114A1.002](https://doi.org/10.5067/VIIRS/VJ114A1.002), [NASA CMR](https://cmr.earthdata.nasa.gov/search/) | 1,819 available daily h19v05 sources, 2018–2022, native FireMask and QA subsets; 163 matched training cells from a 326-cell panel | Earthdata token. Seven requested calendar dates have no catalogue source. Daily nominal 1 km target; cloud/processed-area screening is not continuous observability or true incident ground truth. |
| Additional issued weather | [NASA GEOS-FP forecast archive](https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/forecast/) | 72 hourly regional field subsets from issue 2026-11-14 00 UTC, valid 2026-11-16 00 UTC through 2026-11-17 00 UTC | Public range reads. Actual issue/valid/retrieval timestamps retained. Approximately 0.25° × 0.3125° inputs; actual future inputs do not establish historical operational performance. |

NASA open-data policy and dataset-specific attribution requirements below also
apply to these additions. The Greek paper, supplement and MIT-licensed source code
are methodological references, not permission to substitute its mixed-agency data
for the requested NASA-only predictors.

The 516 recent Lebanese soil point-days overlap the historical archive through
10 November; these are acquisition counts, not 516 additional unique observations.

This supersedes the initial access-only reports. Download manifests alongside raw files record exact NASA URLs, retrieval times, byte sizes and SHA256. CMR catalogues retain collection/granule metadata and processing identities. Retain source citations and consult each collection's current use constraints; this repository does not grant additional rights.

NASA's [Earth science data policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-and-information-policy) supports open use of NASA Earth science data, subject to product-specific terms and proper acknowledgement. NASA data are not covered by the repository's software license. The NASA-hosted country geometry has no separately verified geometry-specific license in this run; retain its origin and verify redistribution terms before republishing it as a standalone border dataset.

| Obtained source | NASA URL / product | Actual coverage and resolution | Access and material limitations |
|---|---|---|---|
| FIRMS country detection files | [Catalogue](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt), [attributes](https://firms.modaps.eosdis.nasa.gov/data/country/AttributesReadme.txt) | 48 Lebanon CSVs; 2,234 MODIS detections 2000–2025, 9,926 S-NPP detections 2012–2025, 5,786 NOAA-20 detections 2018–2025 | Public historical country route. MODIS nominal 1km and VIIRS 375m differ in confidence, coverage and observation times. Raw platform/type/processing fields retained. Missing detections do not prove no fire. |
| S-NPP daily fire/cloud/QA masks | [VNP14A1.002 CMR](https://cmr.earthdata.nasa.gov/search/collections.json?concept_id=C2545314541-LPCLOUD) | 10,119 daily tiles, h20v05/h21v05, 2012–2025; nominal 1km sinusoidal grid | Earthdata token. VIIRS 750m-band fire algorithm aggregated to 1km, **not FIRMS 375m labels**. Missing, cloud and unknown classes explicitly handled. Separate historical benchmark; NASA catalogue reports S-NPP science delivery ceased 2 November 2026. |
| NOAA-20 daily fire/cloud/QA masks | [VJ114A1.002 CMR](https://cmr.earthdata.nasa.gov/search/collections.json?concept_id=C2545310874-LPCLOUD) | 5,825 daily tiles, same two tiles, 2018–2025, nominal 1km | Earthdata token. Primary current-target candidate, kept separate from S-NPP. Label probability is conditioned on at least 80% processed eligible area; daily composites are not continuous observation. |
| NASA POWER meteorology | [Daily API documentation](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) | 12 sampled points, 61,368 point-days, 2012–2025 UTC; MERRA-2 meteorology roughly 0.5° × 0.625° | Public. T2M, T2M_MAX, RH2M, PRECTOTCORR, WS10M, WD10M. Original units/header retained. Observed/reanalysis-derived historical weather, not forecasts. Latency varies; training availability was not historically verified. Current rainfall must actually have been retrieved before prediction. |
| NASA POWER cloud history | Same API, SYN1DEG source | Four sampled points, 20,456 point-days, 2012–2025; daily CLOUD_AMT, CLOUD_AMT_DAY, CLOUD_AMT_NIGHT percentages | Public. Coarse daily context; never used as exact satellite-overpass coverage evidence. No historical availability timestamps invented. |
| NASA GEOS FP forecast | [Public issue archive](https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/forecast/), [forecast service](https://www.nccs.nasa.gov/geos5-forecast/) | Actual cycle 2026-11-14 00 UTC; complete 24h target 2026-11-15 UTC. 72 regional NetCDF subsets: SLV temperature/humidity/pressure/wind, FLX precipitation, RAD cloud fraction. Approx. 0.25° × 0.3125°. | Public HTTPS range reads. Save immutable original filename/URL, remote metadata, subset hash and actual retrieval time. Hash is of retained subset, not whole global file. Rolling archive; tested historical 2020 route unavailable. GEOS-CF historical samples inspected did not supply required meteorology. No multi-year issued-forecast weather backtest obtained. |
| NASA MODIS land cover | [MCD12Q1.061](https://www.earthdata.nasa.gov/data/catalog/lpcloud-mcd12q1-061), [collection-6 guide](https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCD12_User_Guide_V6.pdf) | Two actual 2010 tiles; 500m annual IGBP classes and categorical QC | Earthdata token. Fixed pre-target ecological reconstruction; downloaded collection was reprocessed in 2022, so its historical version availability is not proven. Accept exact QC categories, exclude uncertain classes. Cropland included; static 2010 cover cannot describe all later land-use changes. |
| NASA terrain | [SRTMGL1.003](https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003) | Four 1° HGT tiles covering Lebanon, nominal 1 arcsecond / 30m; acquisition 2000 | Earthdata token. Void sentinel rejected; derive metre-aware slope and aspect at native sample points before cell averaging. Nine terrain samples per eligible nominal 1km pixel; not exhaustive parcel-scale terrain/fuel detail. |
| NASA-served Lebanon analysis geometry | [FIRMS world countries GeoJSON](https://firms.modaps.eosdis.nasa.gov/content/geodata/world_countries.geojson) | Lebanon ISO_3DIGIT LBN; used for in-country pixel masking and clipped output | Public. NASA map geometry, not a legal-border assertion. Product-specific redistribution terms not separately established. |
| Sample swath masks/geolocation and vegetation | [CMR](https://cmr.earthdata.nasa.gov/search/site/collections/directory/) VNP14IMG.002, VNP03IMG version 2, MOD13Q1.061 | Real matched 375m swath sample and 250m/16-day vegetation sample | Earthdata token. Real mask/geolocation decoding checked. One swath cannot authorize historical negatives; one NDVI composite cannot stand in for a full historically available NDVI series. Samples are not used to invent missing history. |

## Clouds and non-detections

NASA's [FIRMS FAQ](https://www.earthdata.nasa.gov/data/tools/firms/faq) and source product documentation describe missed fires from clouds, small/cool fires, observation timing and other retrieval limitations. The implemented daily mask distinguishes cloud from processed land and missing/unknown data. Both fitted classes satisfy the same processed-area rule. This reduces one source of label bias but does not establish true-fire absence or unconditional operational detection probability. Smoke and cloud obscuration are not independently reconstructed for every incident.

## Beirut review and non-NASA event sources

The FIRMS query within 3km of the port, 4 August 2020 14:00 to 5 August 18:00 UTC, found **one S-NPP detection** at 2020-08-04 23:35 UTC (33.90074, 35.52045), about 137m from the review centre. This is provisional spatial/temporal association only. The event is retained in the review list; no explosion causation or confirmed non-target classification is invented. The daily target is a different product, so this FIRMS match is not automatically a daily-model positive.

ACLED, DesInventar, EM-DAT and UN reports were investigated as initial review candidates, but no usable licensed event catalogue was acquired or incorporated. ACLED access was blocked; useful Lebanon export/precision/terms for the other catalogues were not established. The later NASA-only instruction excludes acquiring these as model data. Consequently facility, conflict, managed-burning and disaster attribution are incomplete. Source type/confidence and training-era recurring-location flags remain auditable review proxies, not causal certification. No full burned-area validation or infrastructure dataset was downloaded.

## Comparable regions

No real regional training experiment has been completed. Lebanon remains primary; no entire neighboring country is assumed ecologically equivalent. `compare_profiles` can compare pre-test rainfall, temperature, seasonality, vegetation, elevation and coverage-normalized fire profiles. Candidate strata need actual profile/coverage evidence and geographic deduplication before inclusion. Synthetic Cyprus examples do not establish transfer benefit. Global and deep-learning experiments are deferred because current labels and operational validation are more limiting than algorithm complexity.

## Completed global extension and user-authorized conflict review

The [latest global report](global-results.md) supersedes Lebanon-only scope for the
new experiment. NOAA-20 VJ114A1.002, MCD12Q1.061, SRTMGL1.003 and NASA POWER were
acquired for 24 predeclared globally distributed panels. Exact selected raw arrays
and QA are retained with immutable source URLs, original/subset hashes and dates;
this is scientific subsetting, not retention of every full global source container.
New global 2026 collection has 479 available tile/date sources out of 480 requested;
missing evidence does not become a negative label.

The user's later conflict instruction explicitly authorizes historical sources
outside NASA for exclusion review. [CDR/OCHA Lebanon COD boundaries](https://data.humdata.org/dataset/cod-ab-lbn),
ADM1 version v02 (valid_on 2024-11-13), provide South LB6 and El Nabatieh LB4.
The exact standard `lbn_admin1.geojson` layer is used, not the separate edge-matched
layer. License: [CC BY-IGO 3.0](http://creativecommons.org/licenses/by/3.0/igo/legalcode).
Credit Council for Development and Reconstruction (CDR), distributed by OCHA on HDX.
The raw archive/API response, hash and version are cached. A 1km metric buffer and
whole-cell temporal overlap define the user-requested broad quarantine from
2023-10-07 00:00 UTC. These fields are historical label/evaluation quality only,
never predictors or asserted real-time 2023 boundary availability.

[ACLED access documentation](https://acleddata.com/faq/how-can-i-access-and-use-acled-data)
requires authorized registration; its [codebook](https://acleddata.com/methodology/acled-codebook)
and [update methodology](https://acleddata.com/methodology/keeping-acled-data-updated)
describe aggregation/revisions and limitations. No complete accessible strike-to-fire
inventory was established. [Official UN reporting](https://www.un.org/sg/en/content/highlight/2024-10-16.html)
also documents activity beyond the southern governorates. The broad regional mask
neither establishes event causation nor certifies the remainder of Lebanon clean.
All fire/weather/vegetation/terrain predictors in this extension remain NASA-only.
