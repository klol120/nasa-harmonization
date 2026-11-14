# Lebanon satellite-detected vegetation-fire occurrence

**Real NASA data have been downloaded, transformed, trained and evaluated. The model is a retrospective research model; production release is blocked.** Read the [actual results](docs/current-results.md), [complete statecharts](docs/statecharts.md), [source ledger](docs/sources.md) and [decisions](../decisions.md).

Estimate whether vegetation-associated fire will be **detected by the configured satellite product** in an eligible Lebanese grid cell during the next 24-hour UTC window. This includes continuing fires and agricultural burning. It does not predict fire spread, damage or whether fire will reach infrastructure. It is not an emergency warning system.

## Actual completed run

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
