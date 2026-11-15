> Historical stage snapshot. Superseded for current run status by [actual results](current-results.md) and [production status](production-status.json). Earthdata access and real retrospective training now succeeded.

# NASA-only data acquisition — 14 November 2026

This update supersedes the initial statement that no real daily fire data was available.
The earlier inspection missed FIRMS' **public country-year download route**. Its files
are called yearly summaries, but they contain individual detections with acquisition
dates/times, not merely yearly totals. Login is unnecessary for this route. The
custom archive request interface does require authentication; that restriction did
not justify treating all historical FIRMS access as blocked.

All new downloaded datasets come from NASA-hosted endpoints. Non-NASA data candidates
in the original source investigation are outside the user's revised scope. MODIS and
VIIRS are the instruments; FIRMS is NASA's distribution service. NOAA-20 is a NOAA
satellite carrying VIIRS, with its fire data distributed by NASA FIRMS.

## Downloaded and validated

| Product | Available Lebanon files downloaded | Individual detection rows |
|---|---|---:|
| MODIS, Terra/Aqua | 2000–2025, 26 files | 2,234 |
| VIIRS S-NPP | 2012–2025, 14 files | 9,926 |
| VIIRS NOAA-20 / JPSS-1 | 2018–2025, 8 files | 5,786 |
| **Total** | **48 annual files** | **17,946** |

The first actual MODIS detection in these files is 2000-11-13, and the final VIIRS
S-NPP detection is 2025-12-29. No detections on earlier/later days do not establish
sensor availability or absence of fire. Original product versions, satellite IDs,
confidence, type, fire radiative power and pixel scan/track attributes are preserved.
There are zero identical within-product/platform/version/location/time duplicates
under the explicit duplicate check; this does not establish incident independence.

NASA POWER: daily history from **2012-01-01 through 2025-12-31** at 12 coarse sample
points spanning Lebanon's bounding rectangle: **61,368 point-days**, six meteorological
variables each, no missing supplied parameter values. The variables are mean and
maximum 2 m temperature (°C), 2 m relative humidity (%), corrected precipitation
(mm/day), and 10 m wind speed (m/s) and direction (degrees). The response identifies
MERRA-2 and POWER sources and UTC daily intervals. An additional seven-day preceding
rainfall sum excludes the current day; its first seven days per point are null.
Wind u/v use the meteorological direction-from convention. These are historical
observed/reanalysis-derived estimates, not issued weather forecasts. Historical
publication availability has not been verified, so recent history must be appropriately
lagged before real forecasting features are constructed.

These 12 points are a bounding-rectangle sampling scheme, not a Lebanese national
mask or evidence of 12 independent meteorological grid cells. Weather is coarse
relative to Lebanon's terrain. The full acquisition report carries provider units,
source/version metadata, URLs, file hashes, byte sizes and missing-value counts.
Each raw download also has an immutable retrieval-time/checksum manifest.

## Beirut port review

Queried the downloaded 2020 MODIS, S-NPP and NOAA-20 files for detections within
3 km of 33.901 N, 35.519 E and the half-open UTC interval
2020-08-04 14:00 to 2020-08-05 18:00. **One detection** matched: S-NPP at
2020-08-04 23:35 UTC, 33.90074 N, 35.52045 E, about 0.137 km from the reference
point. Its original source type is retained. This establishes a spatial/temporal
match, **not** explosion causation or a vegetation-fire classification. The envelope
is provisional; further source-specific temporal/footprint review is needed before
changing a label. The hit is not automatically inserted as a confirmed exclusion.

## Weather forecasts and remaining data access

NASA GEOS forecast root currently lists only Y2026; the tested Y2020 forecast path
returns 404. OPeNDAP lists current `.latest` collections rather than a verified
2012–2025 issued archive. The acquisition command also attempts one explicitly
issue-indexed GEOS NetCDF4 sample (issue 2026-11-14 00 UTC; hourly valid midpoint
2026-11-15 00:30 UTC). The 48,333,556-byte NetCDF4 file was downloaded and its HDF5 signature and checksum
were validated. See the generated acquisition report for its exact byte size/hash.
That single snapshot cannot support a multi-year evaluation, nor does it cover a
whole daily forecast window. Historical dissemination latency remains unverified.

Full MODIS MOD14 observation masks are listed publicly, but an actual granule download
redirects to NASA Earthdata login. An unauthenticated protected NASA land-cover
request returns 401. Thus **clear-land/satellite observability and vegetation/terrain
integration remain incomplete**. No-detection days are not converted into training
negatives. No new real-data training or evaluation is claimed.

The proposed untouched test period is **2023–2025**, with **2012–2020 training** and
**2021–2022 validation**, plus boundary embargoes. This design is recorded in
`configs/nasa-split-plan.json`. It is a reservation for a future valid experiment,
not a completed split/training run. Prefer stable S-NPP labels first and preserve
other platforms for separately reported sensitivity analysis.

## Reproduce / inspect

From `forecasting/`:

```sh
uv sync --frozen --extra dev
uv run python -m firecast.acquire --config configs/nasa-acquisition.json --out data/nasa-lebanon
uv run pytest -q
```

The config selects countries, products, years, weather points/parameters/dates and
an optional dated GEOS sample. Files already present are verified against their
manifests and reused. At most three FIRMS/two POWER downloads run concurrently;
transient errors retry. NASA country-file inventory sizes are checked against downloads.
Never replace the dated GEOS sample with an unstamped mutable `.latest` training source.
The recent GEOS archive may eventually drop this sample; the original cached file
and manifest then preserve the exact acquired version.

Outputs under ignored `data/nasa-lebanon/`:

* `raw/firms/`: original 48 CSVs, inventory, NASA attribute/license readme and manifests.
* `raw/power/`: original API JSON responses and manifests.
* `raw/geos/`: optional real forecast sample and manifest, if obtained.
* `detections_raw_combined.csv`: concatenated source columns plus acquisition time/provenance.
* `detections.csv`: pipeline columns plus original provider attributes; flags are not yet adjudicated.
* `weather_historical.csv`: validated daily weather and explicitly preceding rainfall.
* `fire_counts_by_year.csv`, `beirut_port_review_hits.csv`, `acquisition-report.json`.

The source license guidance is preserved in NASA's `AttributesReadme.txt`; follow
NASA FIRMS attribution/disclaimer and POWER attribution guidance. No secrets or
large raw files were added to git. Reusable logic is in `src/firecast/acquire.py`;
source-specific tests cover timestamps, version/platform retention, byte-size validation,
missing-value sentinels, UTC enforcement and preceding-rainfall alignment.

Validation after acquisition: all 17 tests passed; Python compilation, raw-file
checksum verification and `git diff --check` passed. Nothing was pushed or deployed.
