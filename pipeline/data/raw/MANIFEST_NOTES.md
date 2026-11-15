## Notes and known gaps

- **Northern Cyprus is not covered by the archives.** FIRMS publishes no country file for it (all name variants 404),
  and neither the Cyprus nor the Turkey file contains detections on that part of the island. The `Cyprus`
  donor therefore covers the Republic of Cyprus only (lat <= ~35.2 N). The 2026 API files do include it.
- **Area API accepts DAY_RANGE 1-5 only** ("Invalid day range. Expects [1..5]." for 10).
- **acq_time**: zero-padded in archives (`0932`), unpadded in the API (`953`).
- **confidence**: MODIS 0-100 integer; VIIRS `l`/`n`/`h`.
- **Brightness columns**: MODIS `brightness`, `bright_t31`; VIIRS `bright_ti4`, `bright_ti5`.
- **MODIS `version` varies across years** (e.g. `6.2` in 2002, `6.03` in 2020, `61.03` in 2025); keep it for the
  processing-change break checks (2018, 2023) in the method.
- **type**: present in both archive and API SP files (0 vegetation, 2 other static land, 3 offshore).
- MODIS_SP starts 2000-11-01 (first Lebanon detection 2000-11-13); VIIRS_SNPP_SP starts 2012-01-20.

## Same footprint for every year (2026 area-API data)

The area API returns everything in the bbox, the archives only the listed countries. To keep the area
constant across years, the 2026 API files are clipped to the archive footprint:

- Each API detection is tagged with a country by `tools/footprint.py`: point-in-polygon on Natural Earth 10m
  admin-0 (`data/ext/ne_10m_admin_0_countries.zip`); a point in NE's sea takes the nearest NE country if
  within 12 km (`download.max_sea_km`). The 12 km comes from the archives: their finer coastline puts
  near-shore Greece/Turkey detections in NE's sea (median ~0.2 km, 99% < 3.3 km, max 12 km from NE land).
- Only detections tagged with one of the region's `archive_countries` are kept. Dropped: Northern Cyprus,
  the Cyprus UN buffer zone, Akrotiri and Dhekelia (also absent from the Cyprus archive), Jordan, Iraq,
  Egypt, offshore >12 km, and for Greece the neighbouring Albania, North Macedonia, Bulgaria and Turkey.
- Check against archives on overlapping data (API pull Jul-Aug 2025 for eastmed/greece, Jul 2025 lebanon,
  kept in `api/*/*/2025-*.csv`): the rule reproduced the archive sets exactly for lebanon and greece
  (0 extra, 0 missing) and for eastmed kept 1 extra VIIRS point (Syria) out of 5,754, missing 0.
- Country labels differ from the archives only between Israel and Palestine (14 of ~7,100 eastmed
  detections; 571 of 30,800 over all archive years). Treat Israel/Palestine as one donor group.
