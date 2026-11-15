> Historical stage snapshot. Superseded for current run status by [actual results](current-results.md) and [production status](production-status.json). Earthdata access and real retrospective training now succeeded.

# NASA cloud acquisition and integration

Public NASA POWER cloud history was downloaded for 2012–2025 at four sampling points
(33.5/34.5 N × 35.5/36.5 E). The API identifies SYN1DEG and POWER as its sources.
There are **20,456 point-days**, each with total, daytime and nighttime cloud amount
in percent, and no missing values in these three fields. Source-native resolution is
coarse; the sample coordinates do not provide local mountain/valley cloud precision.

```sh
uv run python -m firecast.clouds --config configs/cloud-acquisition.json --out data/nasa-clouds
```

Original JSON and checksum/download manifests are in ignored `data/nasa-clouds/raw/`.
`cloud_history.csv.gz` preserves missing sentinels as nulls, enforces UTC and percent
units, and rejects out-of-range values. `cloud-report.json` records parameters,
provider metadata, provenance and the explicit `coverage_evidence_qualified: false`.

`attach_cloud_context` links the four cloud points to the existing weather samples
by great-circle distance and exact date. The resulting historical context file has
61,368 weather/cloud rows with no missing cloud amount values. It does not backdate
cloud publication: `cloud_available_at` remains null. NASA observation date is not a
proof of publication/availability at a past prediction time. Do not feed target-day
observed cloud amounts into an operational forecast backtest.

Daily cloud means do not identify clouds at the exact MODIS/VIIRS overpass, satellite
outages, scan gaps, swath QA or the vegetation area actually observable. A low cloud
percentage therefore does not authorize a negative label. The protected masks and
matching geolocation are the remaining satellite-observation acquisition dependency.

`masks.swath_evidence` is a fixture-tested HDF5 adapter for matched VNP14IMG/VNP03IMG
acquisitions. It reads geographic swath chunks and counts cloud, clear-land and fire
classes in each candidate cell, preserving the acquisition time. It explicitly refuses
to qualify that sampled-pixel evidence as complete daily coverage. Full QA, eligible
area, expected overpasses and daily assembly must still be validated on real files.
No browse-image colors are used as science measurements.

NASA references:

* https://power.larc.nasa.gov/docs/services/api/
* https://power.larc.nasa.gov/api/system/manager/parameters?community=AG&temporal=daily
* https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14IMG
* https://urs.earthdata.nasa.gov/documentation/for_users/user_token

The fifth notebook executes this cloud-data inspection, decodes the real GEOS sample
and shows the current failed release checks. Its plots use training years only.
