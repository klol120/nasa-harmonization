# Lebanon satellite-detected vegetation-fire occurrence

**Completed: global NASA pretraining, Greek/Lebanese adaptation, temporal LSTMs, external NASA-pretrained encoder comparisons and southern-conflict exclusions. Production release remains blocked.** Read the [2016–2017 evaluation](docs/older-evaluation-results.md), [older-evaluation statecharts](docs/older-evaluation-statecharts.md), [pretrained experiment](docs/pretrained-results.md), [Greek temporal results](docs/greek-experiment-results.md), [source ledger](docs/sources.md) and [decisions](../decisions.md). The [earlier global results](docs/global-results.md) and [Lebanon-only results](docs/current-results.md) remain historical baselines.

The [literature review](docs/literature-review.md) compares six published fire-model
studies and explains high reported scores, task/sampling differences and proposed
NASA-only improvements. Its [metric diagnostic](docs/literature-metric-context.json)
reuses the frozen global model without training or changing thresholds.

The [Greek-study focus](docs/greek-study-focus.md) is the main methodological
reference for the completed temporal experiments. It includes an executed NASA comparison of
Greek and Lebanese development weather/terrain, pinned source-code settings and
explicit differences from the paper's target, sampling and forecast assumptions.

The [Greek-inspired temporal experiment](docs/greek-experiment-results.md) now fits
actual LSTM models, tree/linear controls, daily Greek labels, NASA NDVI/wetness
histories and frozen transfer stages. Read its [statecharts](docs/greek-temporal-statecharts.md).

The [external-pretrained encoder experiment](docs/pretrained-results.md) compares
three published IBM/NASA Prithvi checkpoints adapted to Lebanese occurrence labels.
Read the [source/license review](docs/pretrained-sources.md) and
[adaptation statecharts](docs/pretrained-statecharts.md). These are image encoders
with new occurrence heads; their historical tests remain retrospective diagnostics.

Estimate whether vegetation-associated fire will be **detected by the configured satellite product** in an eligible Lebanese grid cell during the next 24-hour UTC window. This includes continuing fires and agricultural burning. It does not predict fire spread, damage or whether fire will reach infrastructure. It is not an emergency warning system.

## Original Lebanon-only baseline

* 17,946 NASA FIRMS MODIS/VIIRS detections, 2000–2025, preserved with original sensor/version fields.
* 10,119 S-NPP VNP14A1 daily tiles, 2012–2025; separate 5,825 NOAA-20 VJ114A1 daily tiles, 2018–2025.
* 61,368 NASA POWER meteorology point-days and 20,456 POWER/SYN1DEG cloud point-days, 2012–2025.
* Real MCD12Q1.061 land cover, SRTMGL1.003 elevation and NASA-served Lebanon analysis geometry.
* A complete actual GEOS forecast window: 72 regional subsets covering 24 hours of meteorology, rainfall and clouds, issued 14 November 2026 for 15 November.
* Both platforms fitted separately. The primary NOAA-20 strict-policy winner is environmental logistic regression, selected by validation Brier. The reserved 2023–2025 test contains 120,155 qualified windows / 280 positive windows. Test average precision is 0.00909 versus seasonal baseline 0.00410; threshold precision is only 0.0131 and recall 0.0964. These results do **not** support operational alerts.

The model was fitted to observed historical POWER weather, not archived issued forecasts. Live GEOS inference is explicitly flagged as unvalidated source transfer. Full historical forecast availability, incident independence and satisfactory calibration remain unresolved. A real release assessment records `approved: false`; the API refuses to serve this artifact as an approved operational model.

## Setup and authentication

Run commands below from `forecasting/`. Use Python 3.12 and the checked-in lock:

```sh
uv sync --frozen --extra dev
uv run --frozen pytest -q
```

CPU is sufficient; no GPU/database is required. Allow roughly 4 GB RAM and 12–16 GB free disk for both archives, Python dependencies, intermediate files and a container build. Downloads are a few GB; latency and NASA service limits determine run time. Training takes minutes, not hours, on an ordinary CPU.

Public FIRMS country files, POWER and current GEOS forecasts need no key. Protected fire masks/land-cover/terrain files require a valid [NASA Earthdata user token](https://urs.earthdata.nasa.gov/documentation/for_users/user_token) and applicable NASA application authorization. Save it securely **outside the repository**, in a file readable only by its owner, and set `EARTHDATA_TOKEN_FILE` to that file's path. Pass the path, never a credential value, on the command line. Do not paste tokens into chat, notebooks or configs. Rotate any token already disclosed. The optional swath sample command accepts `EARTHDATA_TOKEN` from the process environment. `FIRMS_MAP_KEY` is only for a separate FIRMS NRT API route, not the downloaded public historical country files. `.env.example` contains names only and is not loaded automatically.

## Reproduce acquisition and real training

```sh
uv run --frozen python -m firecast.acquire --config configs/nasa-acquisition.json --out data/nasa-lebanon
uv run --frozen python -m firecast.clouds --config configs/cloud-acquisition.json --out data/nasa-clouds
uv run --frozen python -m firecast.environment_acquire --plan configs/environment-sources.json --out data/environment --token-file "$EARTHDATA_TOKEN_FILE"
uv run --frozen python -m firecast.gridded_acquire --config configs/noaa20-acquisition.json --out data/gridded-noaa20 --token-file "$EARTHDATA_TOKEN_FILE"
uv run --frozen python -m firecast.gridded --data data/nasa-lebanon --environment data/environment --fire-archive data/gridded-noaa20 --config configs/noaa20-dataset.json --out outputs/noaa20-real
uv run --frozen python -m firecast.train_real --data outputs/noaa20-real --out outputs/noaa20-real/models
uv run --frozen python -m firecast.review --data outputs/noaa20-real --models outputs/noaa20-real/models --out outputs/noaa20-real/review
uv run --frozen python -m firecast.statecharts --readiness outputs/noaa20-real/dataset-report.json --out docs/statecharts.md
```

For the S-NPP benchmark repeat the gridded commands using `configs/gridded-acquisition.json`, `data/gridded-fire`, `configs/gridded-dataset.json` and `outputs/gridded-real`. Never pool these labels into a fictional stable sensor history. `gridded_acquire --catalog-only` checks source inventory without downloading. Existing validated raw caches can be copied into the documented paths for offline transformation/training; checksums/manifests must accompany them. Partial archives are rejected. Source files remain unchanged, downloads are restartable, and every original/subset has a URL, retrieval time and SHA256 manifest.

Configuration controls grid, region, dates, product, eligibility and review policy. This actual daily-composite adapter **only supports 24-hour UTC windows** and rejects other horizons. The generic normalized-input pipeline supports configurable horizons, but other real horizons need a new compatible label/weather aggregation and evaluation. Do not merely change an output timestamp.

The grid is 0.1° (about 11.1 km north–south and 9.2 km east–west at Lebanon). It aggregates nominal 1km fire pixels; it does not provide 375m forecast precision. GEOS is approximately 0.25° × 0.3125° and POWER meteorology roughly 0.5° × 0.625°; repeated fine-grid rows do not constitute independent weather observations. The 124 eligible cells cover selected vegetated portions of NASA's Lebanon analysis geometry, not every land parcel.

## Forecast inputs and inference

For the completed issue/window, cached inputs already exist. For another **future** window, choose an available GEOS cycle before prediction, download all hours and retain actual retrieval timestamps:

```sh
uv run --frozen python -m firecast.forecast_acquire --issue 2026-11-14T00:00:00Z --prediction-time 2026-11-15T00:00:00Z --horizon 24 --out data/geos-forecast-20261115
uv run --frozen python -m firecast.forecast_features --forecast-dir data/geos-forecast-20261115 --cells outputs/noaa20-real/cells.csv --environment data/environment --out data/live-forecast-features
uv run --frozen firecast predict --model outputs/noaa20-real/models/model.joblib --input data/live-forecast-features/forecast-features.csv --out outputs/live-research-risk
```

This produces `risk.csv`, country-clipped `risk.geojson` and `risk.png`. These are explicitly research estimates conditional on the daily observation-coverage selection. Every current real forecast row retains `RETROSPECTIVE_MODEL_NOT_OPERATIONALLY_VALIDATED`, `outside_validated_weather_source` and `COVERAGE_CONDITIONAL_RESEARCH_ESTIMATE`. Issued time, valid window, actual forecast/history retrieval timestamps, label product and model version are exported. Missing/future/wrong-window inputs suppress probabilities. Add `--lat` and `--lon` to select one supplied eligible cell.

GEOS keeps a rolling public forecast archive. The fixed 2026 example will eventually require its retained cache; it is not a permanent remote reforecast archive. The three-day history lag does not guarantee POWER availability: missing or not-yet-retrieved rainfall is rejected. Existing cached data cannot be backdated to simulate earlier forecast access. F1 thresholds are chosen on validation, are not alert-cost thresholds, and are not approved risk categories. The map's probability scale is displayed explicitly and extends to at least the validation threshold. Optional `firecast overlay` screens supplied point/line assets using approximate buffered bounding boxes; no NASA infrastructure layer was obtained.

## Notebooks, modules and outputs

* `01`–`03`: executed synthetic exploration, transformations and training demonstration, calling the same modules. Synthetic metrics are never Lebanese evidence.
* `04`–`05`: earlier real-data/coverage and cloud/access snapshots, retained as labelled historical stages.
* `06_real_pipeline_and_evaluation.ipynb`: executed real static transformation, label audit, frozen model comparisons, reserved-year evaluation, calibration review, failed release and actual GEOS research map. See its training function call for reproduction.

Reusable modules under `src/firecast/` implement acquisition, raster alignment, labels, models, evaluation, forecast normalization, inference and service. `outputs/noaa20-real/` contains versioned datasets, audit, native-pixel maps, frozen model, full metrics, split manifest, PR/calibration figure and failed release record. Committed `docs/real-metrics.json` and `docs/current-results.json` retain non-secret run evidence; large raw data/models remain local and git-ignored. Never load an untrusted pickle/joblib artifact.

[Deployment instructions](docs/deployment.md) cover the locked non-root container, authentication and release gate. `/healthz` is liveness; `/readyz` and `/forecast` return 503 without a verified operational model. No external deployment has occurred. Raw datasets and generated model artifacts remain local and git-ignored.

## Separate small fixture

With no data access, the complete synthetic mechanics example remains reproducible:

```sh
uv run --frozen firecast fixture --out data/fixture
uv run --frozen firecast run --data data/fixture --config data/fixture/config.json --out outputs/demo
uv run --frozen firecast predict --model outputs/demo/model.joblib --input outputs/demo/inference-example.csv --out outputs/demo/risk
```

[Current results](docs/current-results.md) list remaining scientific work, tested behavior and evidence limitations. [Initial plan review](docs/plan-review.md) explains why monthly exports, naive negatives and immediate deep learning were unsuitable.

## Global pretraining and Lebanon adaptation

The completed global experiment is implemented under `global_acquire.py`, `global_weather.py`,
`global_data.py`, `transfer_models.py` and `benchmark_global.py`. Its fixed design is
`configs/global-benchmark.json`; [global statecharts](docs/global-statecharts.md)
explain scientific subsetting, algorithms, genuine neural weight continuation,
calibration/ensembling, conflict exclusions and the sealed confirmation gate.

`configs/conflict-review.json` implements the user's later instruction to quarantine
South and El Nabatieh from 2023-10-07 onward. The boundary geometry is CDR/OCHA HDX
CC BY-IGO, used solely for historical label/evaluation quality; it is not a model
predictor. Environmental inputs remain NASA-only. A full strike catalogue has not
been obtained; other Lebanese areas may still contain conflict-related detections.

To restore the original daily fire caches after lossless disk compaction:

```sh
uv run --frozen python -m firecast.cache_pack restore --raw data/gridded-fire/raw --packed data/gridded-fire/packed-raw
uv run --frozen python -m firecast.cache_pack restore --raw data/gridded-fire/raw --packed data/gridded-fire/packed-originals
uv run --frozen python -m firecast.cache_pack restore --raw data/gridded-noaa20/raw --packed data/gridded-noaa20/packed-originals
```

Both archive/member hashes are verified. Packed copies are retained. Ensure enough
free disk for restoration; all original science files and provenance bytes are
recoverable. Restoration is required before rebuilding either original daily-file
adapter from those packed caches; the prepared global/temporal tensors and their
scientific subset archives can be used directly without restoration.

## Greek-inspired temporal experiment

This is a NASA-only retrospective adaptation of the Greek methodology. It preserves
the next-24-hour satellite-detected occurrence target, representative evaluation
negatives, QA/cloud exclusions and southern conflict quarantine. It does not
reproduce the paper's selected-negative large-fire-danger target or promise its
precision. Forty-five candidates compare source, local, Greek and continued-transfer
stages. LSTM weights genuinely continue; tree/linear transfer adds a parent score.

Use the base locked environment plus the optional CPU dependencies. Allow at least
16 GB disk and 8–12 GB RAM for a comfortable reproduction; source downloads and
temporary rasters add costs beyond fitting. This workspace used verified raw packing,
Linux memory-backed raster reads and a persistent software cache with symlinks.
Do not delete that software cache while the installed environment references it.

```sh
uv sync --frozen --extra dev
uv pip install --python .venv/bin/python -r requirements-temporal-cpu.txt
uv run --no-sync python -m firecast.temporal_confirmation register
uv run --no-sync python -m firecast.greek_environment soil --out data/greek-soil
uv run --no-sync python -m firecast.greek_environment ndvi --out data/greek-ndvi --token-file "$EARTHDATA_TOKEN_FILE"
uv run --no-sync python -m firecast.global_acquire --config configs/greek-daily-acquisition.json --out data/greek-daily-panel --token-file "$EARTHDATA_TOKEN_FILE" --environment data/environment --existing-archive data/gridded-noaa20 --stage fire --reuse-static-from data/global-panel
uv run --no-sync python -m firecast.temporal_data
uv run --no-sync python -m firecast.benchmark_temporal
```

These commands assume the documented original NASA global/Lebanese caches already
exist. The experiment separately records natural-prevalence calibration in 2021,
validation in 2022 and fourteen-day gaps. A frozen experiment refuses overwriting;
use a new output directory for a new run. `--pretrain-only` may precompute source
LSTMs; numerical training-data/settings hashes verify reuse. Notebook 10 calls the
same modules and reproduces frozen metrics without retraining by default.

The completed registered confirmation can be reproduced after freezing, using its
actual weather and fire caches. This does **not** provide fresh independent evidence:

```sh
uv run --no-sync python -m firecast.global_weather --config configs/greek-confirmation.json --out data/greek-confirmation-weather
uv run --no-sync python -m firecast.global_weather --config configs/greek-confirmation.json --out data/greek-confirmation-local-weather --lebanon-data data/nasa-lebanon
uv run --no-sync python -m firecast.temporal_confirmation prepare --token-file "$EARTHDATA_TOKEN_FILE"
uv run --no-sync python -m firecast.temporal_confirmation score
```

The historical November dates are now viewed. Reproducing them does not make them
fresh again. For a new study, register untouched confirmation dates/scope and their
configuration hashes before fire collection, freeze all model choices, then use
`temporal_confirmation prepare` and `score`. The completed initial registration is
retained in local benchmark artifacts and the result JSON. The November cohort has
zero Lebanese positives and cannot establish recall. The separately identified
known-year benchmark covers 2023–2025 and January–October 2026; it never reselects.

```sh
uv run --no-sync python -m firecast.greek_environment soil --config configs/greek-known-benchmark.json --out data/greek-soil-known
uv run --no-sync python -m firecast.greek_environment ndvi --config configs/greek-known-benchmark.json --out data/greek-ndvi-known --token-file "$EARTHDATA_TOKEN_FILE"
uv run --no-sync python -m firecast.temporal_known_benchmark prepare
uv run --no-sync python -m firecast.temporal_known_benchmark score
uv run --no-sync python -m firecast.publish_temporal
```

Research inference accepts `sequence`/`static` NumPy tensors in the artifact's
recorded feature order, plus CSV location/availability metadata. It never needs a
fire label. Forecast issue and retrieval, history retrieval, vegetation retrieval
and composite end must be available before prediction. The 24-hour forecast window
and ten-day history ending four days before target are checked. Invalid/missing
rows and the attached southern scope yield null probabilities. Use only trusted
local joblib artifacts. This optional interface does not bypass the production API.

```sh
uv run --no-sync python -m firecast.temporal_inference --model outputs/greek-temporal-benchmark/research-lebanon.joblib --inputs inputs.npz --metadata metadata.csv --out outputs/temporal-research --research-only
```

Metadata columns: `cell_id`, `region`, `lat`, `lon`, `prediction_time`,
`forecast_issued_at`, `forecast_available_at`, `forecast_valid_start`,
`forecast_valid_end`, `history_start`, `history_end`, `history_latest_available_at`,
`vegetation_available_at`, `vegetation_composite_end`. All times require a timezone.
Include `static_available_at` for the actual terrain/land-cover snapshot as well.
History variables are temperature °C, max temperature °C, humidity %, daily rain mm,
wind u/v m/s, VPD kPa, and root/surface relative wetness (dimensionless). Static/
current inputs follow the exact feature list in each artifact, including NDVI age
and its previous-value indicator. Missing history is never zero-filled.

`temporal_live` assembled actual NASA GEOS inputs for 16 November 2026 UTC using
the 14 November 00 UTC issue, observed POWER histories and MODIS vegetation. This
is a reproducible research demonstration; a rolling NASA archive may later require
its retained cache. Acquire a complete appropriate GEOS cycle and fresh local
POWER weather/soil files before using it for another future window. It writes CSV,
GeoJSON, JSON and a country-clipped probability map with provenance and limitations.
Actual forecast inputs do not validate a model trained on historical perfect-weather
proxies. Release remains false; ConvLSTM and emergency-warning deployment are not
claimed as completed.

The benchmark measured 89 validation candidates in eight model/architecture groups
and retained 58 stage winners, plus nine conservative-policy controls. The latest
fixed refit used 949,823 global / 260,804 Lebanese fitting windows. Its transfer
approach did not beat the matching local-only control on the 15-positive Lebanese
2026 fold. See [results and limitations](docs/global-results.md); none of these
artifacts is approved for production.

Run the following after the original Lebanese data preparation. Paths are relative
to `forecasting/`; `EARTHDATA_TOKEN_FILE` contains a path, never the token value:

```sh
uv run --frozen python -m firecast.conflict_review --config configs/conflict-review.json --out data/conflict-review
uv run --frozen python -m firecast.global_acquire --config configs/global-benchmark.json --out data/global-panel --token-file "$EARTHDATA_TOKEN_FILE" --environment data/environment --existing-archive data/gridded-noaa20
uv run --frozen python -m firecast.global_weather --config configs/global-benchmark.json --out data/global-weather
uv run --frozen python -m firecast.lebanon_confirmation --config configs/global-benchmark.json --maps outputs/noaa20-real --out data/lebanon-2026-masks --token-file "$EARTHDATA_TOKEN_FILE"
uv run --frozen python -m firecast.global_weather --config configs/global-benchmark.json --out data/lebanon-2026-weather --lebanon-data data/nasa-lebanon
uv run --frozen python -m firecast.global_data --config configs/global-benchmark.json --archive data/global-panel --weather data/global-weather/weather.csv.gz --old-data outputs/noaa20-real --confirmation-masks data/lebanon-2026-masks --old-weather data/nasa-lebanon/weather_historical.csv --new-weather data/lebanon-2026-weather/weather.csv.gz --conflict-config configs/conflict-review.json --conflict-geometry data/conflict-review/southern_governorates.geojson --out outputs/global-transfer-data
uv run --frozen python -m firecast.benchmark_global --data outputs/global-transfer-data --out outputs/global-transfer-benchmark
```

The trainer freezes all choices before opening confirmation files. Those outcomes
are now known; reproducing the experiment does not produce a new untouched test.
Use versioned output directories when changing data/design. Full raw caches with
manifests support offline preparation/training; credentials are needed for new
protected downloads, not for fitting already prepared datasets.

For the fixed recent-data refit, capture the **current run's** validation selection
instead of copying the checked-in snapshot's original commit/selection hash:

```sh
uv run --frozen python -m firecast.refit_transfer freeze-protocol --benchmark outputs/global-transfer-benchmark --out outputs/reproduced-refit-protocol.json
uv run --frozen python -m firecast.global_acquire --config configs/global-confirmation-2026.json --out data/global-panel-2026 --token-file "$EARTHDATA_TOKEN_FILE" --environment data/environment --existing-archive data/gridded-noaa20 --stage fire --reuse-static-from data/global-panel
uv run --frozen python -m firecast.global_weather --config configs/global-confirmation-2026.json --out data/global-2026-weather
uv run --frozen python -c "from firecast.refit_transfer import prepare_fresh; prepare_fresh('configs/global-confirmation-2026.json', 'data/global-panel-2026', 'data/global-2026-weather/weather.csv.gz', 'outputs/global-2026-confirmation-data')"
uv run --frozen python -m firecast.refit_transfer --data outputs/global-transfer-data --benchmark outputs/global-transfer-benchmark --fresh-data outputs/global-2026-confirmation-data --protocol outputs/reproduced-refit-protocol.json --out outputs/global-final-refit --environment data/environment
```

Static raw array reuse shares immutable scientific bytes and copies mutable
metadata. The refit is selected from 2022 validation, fits through 2024 and
calibrates on 2025. Its 2023–2025 source data are training/calibration data, not a
held-out temporal test. Global 2026 was newly held out for the original refit;
Lebanese 2026 is explicitly a repeated fixed-fold comparison.

The actual future-window research interface adds the same history features, then
uses the country-view artifact with southern scope suppression:

```sh
uv run --frozen python -m firecast.transfer_forecast --input data/live-forecast-features/forecast-features.csv --out data/transfer-live-forecast
uv run --frozen firecast predict --model outputs/global-final-refit/lebanon-view-research.joblib --input data/transfer-live-forecast/forecast-features.csv --out outputs/global-final-refit/live-research-risk
uv run --frozen python -m firecast.publish_global --root .
```

The fixed 2026-11-15 example requires cached forecast/history evidence after its
prediction time passes. For a different future date collect a matching complete
GEOS window first; never backdate retrieval or fill unavailable recent history.
Notebooks `07_global_data_and_conflict_quality.ipynb` and
`08_global_transfer_and_confirmation.ipynb` execute the actual raw-quality and
frozen-evaluation paths. Generated models/large scientific subsets stay git-ignored.

Optional independent source audit:

```sh
uv run --frozen python scripts/audit_land_qa.py --out outputs/land-qa-audit.json
```

If the managed environment's home cache is read-only, set `UV_CACHE_DIR` to a
writable directory before `uv lock` / `uv sync`. The lock was updated only to
declare SciPy directly and require neural sample-weight support; fitted runtime
library versions were preserved.

## External pretrained encoders

All commands here run from `forecasting/`, after reproducing the Greek temporal
and known-year tensors above. Install the existing optional CPU requirements
without synchronizing them away:

```sh
uv pip install --python .venv/bin/python -r requirements-temporal-cpu.txt
uv run --no-sync python -m firecast.pretrained_encoder discover
/usr/bin/python3 scripts/acquire_hls_patches.py \
  --cells outputs/noaa20-real/cells.csv \
  --catalog data/pretrained-models/hls-catalog.json \
  --out data/pretrained-models/hls-patches \
  --token-file "$EARTHDATA_TOKEN_FILE"
uv run --no-sync python -m firecast.pretrained_encoder extract
uv run --no-sync python -m firecast.benchmark_pretrained fit
uv run --no-sync python -m firecast.benchmark_pretrained score
uv run --no-sync python -m firecast.publish_pretrained --live
```

The HLS reader requires a system Python with GDAL and numpy (`python3-gdal` and
`python3-numpy` packages on Debian/Ubuntu). It reads authenticated NASA COG windows
without full tile downloads. Runtime used GDAL 3.10.3 and system numpy 2.2.4; model
work uses the existing Python 3.12 CPU environment. Credentials stay outside the
repo. No timm/TerraTorch or remote repository code execution is required.

Allow several GB of RAM. The three source checkpoint files total about 1.04 GB of
network transfer, processed one at a time in RAM and verified against pinned
SHA256/size. Full source weights are not retained locally: exact HLS crops,
pre-normalization tokens, original final LayerNorm parameters, adapted heads and
provenance are retained. Re-extraction for new imagery downloads the pinned
checkpoint again. Local retained data can be used offline for fitting/evaluation;
a full-checkpoint mirror must provide exactly the pinned bytes.

`configs/pretrained-transfer.json` records immutable revisions, seed, fine-tuning
settings, splits and limitations. `fit` refuses to overwrite frozen selections.
`score` verifies frozen artifact hashes and never reselects on tests. Notebook 11
calls the same modules, checks actual pretrained parameter updates and reproduces
a frozen result with labels removed from the prediction input. The research ZIP
is under `outputs/delivery/`; models retain cached-cell landscape tokens and do
not support arbitrary new locations without a compatible image extraction.

Use the committed [measured report](docs/pretrained-results.md), [JSON](docs/pretrained-results.json),
[CSV](docs/pretrained-results.csv) and [statecharts](docs/pretrained-statecharts.md).
Modern encoder availability, potential EO2 image overlap, reprocessing availability,
old small landscape crops, already-viewed tests, sparse independent fires and
observed-weather proxies prevent production approval. No API deployment is made.

## Older-year evaluation: 2016–2017

This scores frozen 2018–2020-trained models without fitting or threshold changes.
NOAA-20 labels are unavailable in these years, so the experiment uses the original
NASA S-NPP VNP14A1.002 labels under both strict and conservative policies. Earlier
S-NPP models already trained on these years are excluded. The last eleven days of
2017 are withheld to keep the existing 14-day gap before the earliest fitting target.

Use the existing CPU environment, protected-source token file and system GDAL
reader from the external-model setup. Run from `forecasting/`:

```sh
uv run --no-sync python -m firecast.older_evaluation discover
uv run --no-sync python -m firecast.greek_environment soil --config configs/older-evaluation.json --out data/older-soil
uv run --no-sync python -m firecast.greek_environment ndvi --config configs/older-evaluation.json --out data/older-ndvi --token-file "$EARTHDATA_TOKEN_FILE"
/usr/bin/python3 scripts/acquire_hls_patches.py --cells outputs/noaa20-real/cells.csv --catalog data/older-pretrained/hls-catalog.json --out data/older-pretrained/hls-patches --token-file "$EARTHDATA_TOKEN_FILE"
uv run --no-sync python -m firecast.older_evaluation check-hls
uv run --no-sync python -m firecast.pretrained_encoder extract --config configs/older-evaluation.json --patches data/older-pretrained/hls-patches --out data/older-pretrained
uv run --no-sync python -m firecast.older_evaluation prepare
uv run --no-sync python -m firecast.older_evaluation score
uv run --no-sync python -m firecast.publish_older
```

The committed config pins this execution's source-model/label hashes. An independent
reproduction can register its own correctly trained artifacts **before inspecting
older results**, using `older_evaluation register --config configs/older-reproduction.json`.
Pass that new config with `--config` to every operation above. Registration refuses
to replace an existing different snapshot and checks fitting dates. New labelled
experiment output directories are also required (`--data`, `--out`); do not silently
reuse an old scored cohort with new models. The original checked-in protocol remains
unchanged. `--rebuild-unscored` is only for correcting an unscored intermediate;
it preserves its old manifest and refuses to overwrite the default scored experiment.

2017 imagery cannot serve as input to a 2016 test. Separate 2015 HLS observations
replace only input tokens; pretrained weights, head weights, preprocessing,
calibration and thresholds stay fixed. Unavailable inputs and quarantined positives
remain excluded. Overlapping NDVI/soil source dates must agree exactly before
deduplication. Existing raw S-NPP caches remain packed and preserved; their audited
label exports can be used directly without restoring all tiles.

Read the [measured results](docs/older-evaluation-results.md), [JSON](docs/older-evaluation-results.json),
[CSV](docs/older-evaluation-results.csv), [statecharts](docs/older-evaluation-statecharts.md)
and executed notebook 12. This is backward-time, cross-sensor retrospective transfer;
modern pretraining and processing were unavailable at historical issue times. It is
not a prospective operational backtest, and it does not promote any model.
