# Raw data manifest

Generated 2026-11-13 by `tools/download_firms.py`. Request log: `download.log` (key redacted).

## Sources
- `MODIS_SP`: MODIS Collection 6.1 standard processing (Terra + Aqua), 1 km.
- `VIIRS_SNPP_SP`: VIIRS S-NPP 375 m standard processing.
- `VIIRS_NOAA20_SP`: VIIRS NOAA-20 (JPSS-1) 375 m standard processing (archive prefix `viirs-jpss1`).
- `VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT`: near-real-time products after the SP max_date (area API only; no `type` column).
- Country archives (full years 2000-2025; NOAA-20 from 2018): `https://firms.modaps.eosdis.nasa.gov/data/country/{prefix}/{year}/{prefix}_{year}_{Country}.csv`. Verbatim copies in `archive/{source}/{Country}_{year}.csv`.
- Area API (2026): `https://firms.modaps.eosdis.nasa.gov/api/area/csv/<KEY>/{source}/{bbox}/5/{date}`. Verbatim chunks in `api/{region}/{source}/`.

## Regions
| region | bbox (W,S,E,N) | archive countries |
|---|---|---|
| lebanon | 35.00, 33.00, 36.70, 34.75 | Lebanon |
| greece | 19.20, 34.70, 29.80, 41.80 | Greece |
| eastmed | 30.00, 29.40, 42.40, 38.00 | Lebanon, Syria, Israel, Palestine, Cyprus, Turkey |

Region files `{region}/{source}_{year}.csv` = the listed countries' archive files concatenated, clipped to the bbox, with an added `country` column. `{region}/{source}_{year}_api.csv` = API detections in the bbox, country-tagged with Natural Earth (`tools/footprint.py`) and limited to the same archive countries, so every year covers the same area.

## Files
| region | source | year | origin | rows | first | last |
|---|---|---|---|---|---|---|
| eastmed | MODIS_SP | 2000 | country archive | 466 | 2000-11-01 | 2000-12-31 |
| eastmed | MODIS_SP | 2001 | country archive | 5279 | 2001-01-01 | 2001-12-25 |
| eastmed | MODIS_SP | 2002 | country archive | 6284 | 2002-01-08 | 2002-12-31 |
| eastmed | MODIS_SP | 2003 | country archive | 7668 | 2003-01-02 | 2003-12-31 |
| eastmed | MODIS_SP | 2004 | country archive | 5176 | 2004-01-01 | 2004-12-31 |
| eastmed | MODIS_SP | 2005 | country archive | 5540 | 2005-01-01 | 2005-12-30 |
| eastmed | MODIS_SP | 2006 | country archive | 5623 | 2006-01-01 | 2006-12-31 |
| eastmed | MODIS_SP | 2007 | country archive | 6573 | 2007-01-01 | 2007-12-31 |
| eastmed | MODIS_SP | 2008 | country archive | 4337 | 2008-01-02 | 2008-12-31 |
| eastmed | MODIS_SP | 2009 | country archive | 10200 | 2009-01-02 | 2009-12-31 |
| eastmed | MODIS_SP | 2010 | country archive | 8550 | 2010-01-02 | 2010-12-31 |
| eastmed | MODIS_SP | 2011 | country archive | 7427 | 2011-01-03 | 2011-12-31 |
| eastmed | MODIS_SP | 2012 | country archive | 5717 | 2012-01-03 | 2012-12-31 |
| eastmed | MODIS_SP | 2013 | country archive | 10213 | 2013-01-01 | 2013-12-28 |
| eastmed | MODIS_SP | 2014 | country archive | 5347 | 2014-01-02 | 2014-12-31 |
| eastmed | MODIS_SP | 2015 | country archive | 14025 | 2015-01-01 | 2015-12-30 |
| eastmed | MODIS_SP | 2016 | country archive | 9937 | 2016-01-01 | 2016-12-31 |
| eastmed | MODIS_SP | 2017 | country archive | 8604 | 2017-01-01 | 2017-12-31 |
| eastmed | MODIS_SP | 2018 | country archive | 5234 | 2018-01-02 | 2018-12-30 |
| eastmed | MODIS_SP | 2019 | country archive | 10905 | 2019-01-05 | 2019-12-31 |
| eastmed | MODIS_SP | 2020 | country archive | 9535 | 2020-01-01 | 2020-12-31 |
| eastmed | MODIS_SP | 2021 | country archive | 7220 | 2021-01-01 | 2021-12-31 |
| eastmed | MODIS_SP | 2022 | country archive | 3508 | 2022-01-01 | 2022-12-31 |
| eastmed | MODIS_SP | 2023 | country archive | 6803 | 2023-01-01 | 2023-12-31 |
| eastmed | MODIS_SP | 2024 | country archive | 8654 | 2024-01-01 | 2024-12-29 |
| eastmed | MODIS_SP | 2025 | country archive | 5425 | 2025-01-02 | 2025-12-28 |
| eastmed | MODIS_SP | 2026 | area API | 3544 | 2026-01-03 | 2026-08-31 |
| eastmed | VIIRS_NOAA20_NRT | 2026 | area API | 16185 | 2026-08-01 | 2026-11-13 |
| eastmed | VIIRS_NOAA20_SP | 2018 | country archive | 24730 | 2018-04-01 | 2018-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2019 | country archive | 54980 | 2019-01-01 | 2019-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2020 | country archive | 47072 | 2020-01-01 | 2020-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2021 | country archive | 37036 | 2021-01-01 | 2021-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2022 | country archive | 24568 | 2022-01-01 | 2022-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2023 | country archive | 36433 | 2023-01-01 | 2023-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2024 | country archive | 44534 | 2024-01-01 | 2024-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2025 | country archive | 28988 | 2025-01-01 | 2025-12-31 |
| eastmed | VIIRS_NOAA20_SP | 2026 | area API | 13616 | 2026-01-01 | 2026-07-31 |
| eastmed | VIIRS_SNPP_NRT | 2026 | area API | 14958 | 2026-08-01 | 2026-11-02 |
| eastmed | VIIRS_SNPP_SP | 2012 | country archive | 29554 | 2012-01-20 | 2012-12-31 |
| eastmed | VIIRS_SNPP_SP | 2013 | country archive | 43153 | 2013-01-01 | 2013-12-31 |
| eastmed | VIIRS_SNPP_SP | 2014 | country archive | 27114 | 2014-01-01 | 2014-12-31 |
| eastmed | VIIRS_SNPP_SP | 2015 | country archive | 51378 | 2015-01-01 | 2015-12-31 |
| eastmed | VIIRS_SNPP_SP | 2016 | country archive | 41094 | 2016-01-01 | 2016-12-31 |
| eastmed | VIIRS_SNPP_SP | 2017 | country archive | 38212 | 2017-01-01 | 2017-12-31 |
| eastmed | VIIRS_SNPP_SP | 2018 | country archive | 27658 | 2018-01-01 | 2018-12-31 |
| eastmed | VIIRS_SNPP_SP | 2019 | country archive | 56044 | 2019-01-01 | 2019-12-31 |
| eastmed | VIIRS_SNPP_SP | 2020 | country archive | 49081 | 2020-01-01 | 2020-12-31 |
| eastmed | VIIRS_SNPP_SP | 2021 | country archive | 36159 | 2021-01-01 | 2021-12-31 |
| eastmed | VIIRS_SNPP_SP | 2022 | country archive | 23397 | 2022-01-01 | 2022-12-31 |
| eastmed | VIIRS_SNPP_SP | 2023 | country archive | 35985 | 2023-01-01 | 2023-12-31 |
| eastmed | VIIRS_SNPP_SP | 2024 | country archive | 41097 | 2024-01-01 | 2024-12-31 |
| eastmed | VIIRS_SNPP_SP | 2025 | country archive | 28286 | 2025-01-01 | 2025-12-31 |
| eastmed | VIIRS_SNPP_SP | 2026 | area API | 12458 | 2026-01-01 | 2026-07-31 |
| greece | MODIS_SP | 2000 | country archive | 92 | 2000-11-01 | 2000-12-30 |
| greece | MODIS_SP | 2001 | country archive | 1840 | 2001-01-06 | 2001-12-31 |
| greece | MODIS_SP | 2002 | country archive | 884 | 2002-01-09 | 2002-11-29 |
| greece | MODIS_SP | 2003 | country archive | 1628 | 2003-01-05 | 2003-12-09 |
| greece | MODIS_SP | 2004 | country archive | 2124 | 2004-01-25 | 2004-12-27 |
| greece | MODIS_SP | 2005 | country archive | 1820 | 2005-01-05 | 2005-12-19 |
| greece | MODIS_SP | 2006 | country archive | 1427 | 2006-01-13 | 2006-12-30 |
| greece | MODIS_SP | 2007 | country archive | 6185 | 2007-01-06 | 2007-12-27 |
| greece | MODIS_SP | 2008 | country archive | 2729 | 2008-01-12 | 2008-12-29 |
| greece | MODIS_SP | 2009 | country archive | 1805 | 2009-01-01 | 2009-12-31 |
| greece | MODIS_SP | 2010 | country archive | 930 | 2010-01-01 | 2010-12-24 |
| greece | MODIS_SP | 2011 | country archive | 2655 | 2011-01-08 | 2011-12-21 |
| greece | MODIS_SP | 2012 | country archive | 2156 | 2012-01-05 | 2012-12-27 |
| greece | MODIS_SP | 2013 | country archive | 1816 | 2013-01-03 | 2013-12-23 |
| greece | MODIS_SP | 2014 | country archive | 1362 | 2014-01-11 | 2014-12-28 |
| greece | MODIS_SP | 2015 | country archive | 1322 | 2015-01-02 | 2015-12-29 |
| greece | MODIS_SP | 2016 | country archive | 1677 | 2016-01-08 | 2016-12-30 |
| greece | MODIS_SP | 2017 | country archive | 1513 | 2017-01-02 | 2017-12-30 |
| greece | MODIS_SP | 2018 | country archive | 839 | 2018-01-01 | 2018-12-29 |
| greece | MODIS_SP | 2019 | country archive | 1034 | 2019-01-01 | 2019-12-27 |
| greece | MODIS_SP | 2020 | country archive | 1153 | 2020-01-02 | 2020-12-31 |
| greece | MODIS_SP | 2021 | country archive | 2481 | 2021-01-04 | 2021-12-04 |
| greece | MODIS_SP | 2022 | country archive | 1147 | 2022-01-03 | 2022-12-30 |
| greece | MODIS_SP | 2023 | country archive | 3262 | 2023-01-04 | 2023-12-28 |
| greece | MODIS_SP | 2024 | country archive | 1281 | 2024-01-01 | 2024-12-15 |
| greece | MODIS_SP | 2025 | country archive | 1188 | 2025-01-04 | 2025-12-30 |
| greece | MODIS_SP | 2026 | area API | 644 | 2026-01-11 | 2026-08-27 |
| greece | VIIRS_NOAA20_NRT | 2026 | area API | 1840 | 2026-08-01 | 2026-11-13 |
| greece | VIIRS_NOAA20_SP | 2018 | country archive | 3507 | 2018-04-01 | 2018-12-30 |
| greece | VIIRS_NOAA20_SP | 2019 | country archive | 5151 | 2019-01-01 | 2019-12-31 |
| greece | VIIRS_NOAA20_SP | 2020 | country archive | 4717 | 2020-01-01 | 2020-12-31 |
| greece | VIIRS_NOAA20_SP | 2021 | country archive | 11061 | 2021-01-01 | 2021-12-31 |
| greece | VIIRS_NOAA20_SP | 2022 | country archive | 5031 | 2022-01-02 | 2022-12-31 |
| greece | VIIRS_NOAA20_SP | 2023 | country archive | 10648 | 2023-01-01 | 2023-12-31 |
| greece | VIIRS_NOAA20_SP | 2024 | country archive | 5271 | 2024-01-01 | 2024-12-31 |
| greece | VIIRS_NOAA20_SP | 2025 | country archive | 4177 | 2025-01-01 | 2025-12-31 |
| greece | VIIRS_NOAA20_SP | 2026 | area API | 1986 | 2026-01-02 | 2026-07-31 |
| greece | VIIRS_SNPP_NRT | 2026 | area API | 1947 | 2026-08-01 | 2026-11-02 |
| greece | VIIRS_SNPP_SP | 2012 | country archive | 9264 | 2012-01-20 | 2012-12-29 |
| greece | VIIRS_SNPP_SP | 2013 | country archive | 7368 | 2013-01-02 | 2013-12-31 |
| greece | VIIRS_SNPP_SP | 2014 | country archive | 5980 | 2014-01-03 | 2014-12-29 |
| greece | VIIRS_SNPP_SP | 2015 | country archive | 6050 | 2015-01-02 | 2015-12-30 |
| greece | VIIRS_SNPP_SP | 2016 | country archive | 7642 | 2016-01-01 | 2016-12-30 |
| greece | VIIRS_SNPP_SP | 2017 | country archive | 6153 | 2017-01-01 | 2017-12-31 |
| greece | VIIRS_SNPP_SP | 2018 | country archive | 4015 | 2018-01-01 | 2018-12-31 |
| greece | VIIRS_SNPP_SP | 2019 | country archive | 4962 | 2019-01-01 | 2019-12-31 |
| greece | VIIRS_SNPP_SP | 2020 | country archive | 4503 | 2020-01-01 | 2020-12-31 |
| greece | VIIRS_SNPP_SP | 2021 | country archive | 10552 | 2021-01-01 | 2021-12-29 |
| greece | VIIRS_SNPP_SP | 2022 | country archive | 4566 | 2022-01-01 | 2022-12-31 |
| greece | VIIRS_SNPP_SP | 2023 | country archive | 10475 | 2023-01-02 | 2023-12-29 |
| greece | VIIRS_SNPP_SP | 2024 | country archive | 4630 | 2024-01-01 | 2024-12-31 |
| greece | VIIRS_SNPP_SP | 2025 | country archive | 4282 | 2025-01-01 | 2025-12-31 |
| greece | VIIRS_SNPP_SP | 2026 | area API | 1706 | 2026-01-03 | 2026-07-31 |
| lebanon | MODIS_SP | 2000 | country archive | 2 | 2000-11-13 | 2000-11-13 |
| lebanon | MODIS_SP | 2001 | country archive | 13 | 2001-01-30 | 2001-11-21 |
| lebanon | MODIS_SP | 2002 | country archive | 103 | 2002-02-04 | 2002-11-22 |
| lebanon | MODIS_SP | 2003 | country archive | 52 | 2003-06-15 | 2003-11-04 |
| lebanon | MODIS_SP | 2004 | country archive | 79 | 2004-07-04 | 2004-11-15 |
| lebanon | MODIS_SP | 2005 | country archive | 39 | 2005-05-22 | 2005-12-11 |
| lebanon | MODIS_SP | 2006 | country archive | 193 | 2006-07-01 | 2006-12-10 |
| lebanon | MODIS_SP | 2007 | country archive | 195 | 2007-01-18 | 2007-12-25 |
| lebanon | MODIS_SP | 2008 | country archive | 42 | 2008-03-07 | 2008-12-19 |
| lebanon | MODIS_SP | 2009 | country archive | 70 | 2009-05-08 | 2009-11-08 |
| lebanon | MODIS_SP | 2010 | country archive | 160 | 2010-02-02 | 2010-12-29 |
| lebanon | MODIS_SP | 2011 | country archive | 39 | 2011-07-28 | 2011-12-07 |
| lebanon | MODIS_SP | 2012 | country archive | 56 | 2012-04-02 | 2012-12-01 |
| lebanon | MODIS_SP | 2013 | country archive | 132 | 2013-02-28 | 2013-12-28 |
| lebanon | MODIS_SP | 2014 | country archive | 39 | 2014-04-02 | 2014-11-09 |
| lebanon | MODIS_SP | 2015 | country archive | 58 | 2015-06-01 | 2015-11-23 |
| lebanon | MODIS_SP | 2016 | country archive | 105 | 2016-01-18 | 2016-12-28 |
| lebanon | MODIS_SP | 2017 | country archive | 42 | 2017-03-25 | 2017-12-05 |
| lebanon | MODIS_SP | 2018 | country archive | 38 | 2018-01-09 | 2018-10-30 |
| lebanon | MODIS_SP | 2019 | country archive | 74 | 2019-02-04 | 2019-11-26 |
| lebanon | MODIS_SP | 2020 | country archive | 142 | 2020-05-15 | 2020-11-23 |
| lebanon | MODIS_SP | 2021 | country archive | 134 | 2021-02-11 | 2021-12-11 |
| lebanon | MODIS_SP | 2022 | country archive | 29 | 2022-05-25 | 2022-12-01 |
| lebanon | MODIS_SP | 2023 | country archive | 78 | 2023-01-23 | 2023-12-14 |
| lebanon | MODIS_SP | 2024 | country archive | 229 | 2024-03-02 | 2024-12-08 |
| lebanon | MODIS_SP | 2025 | country archive | 91 | 2025-02-26 | 2025-11-23 |
| lebanon | MODIS_SP | 2026 | area API | 65 | 2026-01-08 | 2026-08-29 |
| lebanon | VIIRS_NOAA20_NRT | 2026 | area API | 387 | 2026-08-01 | 2026-11-12 |
| lebanon | VIIRS_NOAA20_SP | 2018 | country archive | 511 | 2018-04-01 | 2018-12-18 |
| lebanon | VIIRS_NOAA20_SP | 2019 | country archive | 638 | 2019-01-05 | 2019-12-29 |
| lebanon | VIIRS_NOAA20_SP | 2020 | country archive | 849 | 2020-02-02 | 2020-12-28 |
| lebanon | VIIRS_NOAA20_SP | 2021 | country archive | 901 | 2021-01-02 | 2021-12-30 |
| lebanon | VIIRS_NOAA20_SP | 2022 | country archive | 422 | 2022-01-08 | 2022-12-30 |
| lebanon | VIIRS_NOAA20_SP | 2023 | country archive | 628 | 2023-01-02 | 2023-12-29 |
| lebanon | VIIRS_NOAA20_SP | 2024 | country archive | 1223 | 2024-01-03 | 2024-12-21 |
| lebanon | VIIRS_NOAA20_SP | 2025 | country archive | 614 | 2025-01-10 | 2025-12-24 |
| lebanon | VIIRS_NOAA20_SP | 2026 | area API | 227 | 2026-01-06 | 2026-07-31 |
| lebanon | VIIRS_SNPP_NRT | 2026 | area API | 361 | 2026-08-01 | 2026-10-29 |
| lebanon | VIIRS_SNPP_SP | 2012 | country archive | 637 | 2012-01-25 | 2012-12-31 |
| lebanon | VIIRS_SNPP_SP | 2013 | country archive | 946 | 2013-01-01 | 2013-12-29 |
| lebanon | VIIRS_SNPP_SP | 2014 | country archive | 595 | 2014-01-02 | 2014-12-31 |
| lebanon | VIIRS_SNPP_SP | 2015 | country archive | 677 | 2015-01-01 | 2015-12-30 |
| lebanon | VIIRS_SNPP_SP | 2016 | country archive | 880 | 2016-01-05 | 2016-12-30 |
| lebanon | VIIRS_SNPP_SP | 2017 | country archive | 553 | 2017-01-05 | 2017-12-30 |
| lebanon | VIIRS_SNPP_SP | 2018 | country archive | 511 | 2018-01-03 | 2018-12-24 |
| lebanon | VIIRS_SNPP_SP | 2019 | country archive | 590 | 2019-01-17 | 2019-12-29 |
| lebanon | VIIRS_SNPP_SP | 2020 | country archive | 701 | 2020-01-25 | 2020-12-31 |
| lebanon | VIIRS_SNPP_SP | 2021 | country archive | 891 | 2021-01-01 | 2021-12-29 |
| lebanon | VIIRS_SNPP_SP | 2022 | country archive | 447 | 2022-01-04 | 2022-12-30 |
| lebanon | VIIRS_SNPP_SP | 2023 | country archive | 657 | 2023-01-01 | 2023-12-29 |
| lebanon | VIIRS_SNPP_SP | 2024 | country archive | 1257 | 2024-01-02 | 2024-12-26 |
| lebanon | VIIRS_SNPP_SP | 2025 | country archive | 584 | 2025-01-08 | 2025-12-29 |
| lebanon | VIIRS_SNPP_SP | 2026 | area API | 271 | 2026-01-03 | 2026-07-31 |

## Totals
| region | source | origin | rows | first | last |
|---|---|---|---|---|---|
| eastmed | MODIS_SP | area API | 3544 | 2026-01-03 | 2026-08-31 |
| eastmed | MODIS_SP | country archive | 184250 | 2000-11-01 | 2025-12-28 |
| eastmed | VIIRS_NOAA20_NRT | area API | 16185 | 2026-08-01 | 2026-11-13 |
| eastmed | VIIRS_NOAA20_SP | area API | 13616 | 2026-01-01 | 2026-07-31 |
| eastmed | VIIRS_NOAA20_SP | country archive | 298341 | 2018-04-01 | 2025-12-31 |
| eastmed | VIIRS_SNPP_NRT | area API | 14958 | 2026-08-01 | 2026-11-02 |
| eastmed | VIIRS_SNPP_SP | area API | 12458 | 2026-01-01 | 2026-07-31 |
| eastmed | VIIRS_SNPP_SP | country archive | 528212 | 2012-01-20 | 2025-12-31 |
| greece | MODIS_SP | area API | 644 | 2026-01-11 | 2026-08-27 |
| greece | MODIS_SP | country archive | 46350 | 2000-11-01 | 2025-12-30 |
| greece | VIIRS_NOAA20_NRT | area API | 1840 | 2026-08-01 | 2026-11-13 |
| greece | VIIRS_NOAA20_SP | area API | 1986 | 2026-01-02 | 2026-07-31 |
| greece | VIIRS_NOAA20_SP | country archive | 49563 | 2018-04-01 | 2025-12-31 |
| greece | VIIRS_SNPP_NRT | area API | 1947 | 2026-08-01 | 2026-11-02 |
| greece | VIIRS_SNPP_SP | area API | 1706 | 2026-01-03 | 2026-07-31 |
| greece | VIIRS_SNPP_SP | country archive | 90442 | 2012-01-20 | 2025-12-31 |
| lebanon | MODIS_SP | area API | 65 | 2026-01-08 | 2026-08-29 |
| lebanon | MODIS_SP | country archive | 2234 | 2000-11-13 | 2025-11-23 |
| lebanon | VIIRS_NOAA20_NRT | area API | 387 | 2026-08-01 | 2026-11-12 |
| lebanon | VIIRS_NOAA20_SP | area API | 227 | 2026-01-06 | 2026-07-31 |
| lebanon | VIIRS_NOAA20_SP | country archive | 5786 | 2018-04-01 | 2025-12-24 |
| lebanon | VIIRS_SNPP_NRT | area API | 361 | 2026-08-01 | 2026-10-29 |
| lebanon | VIIRS_SNPP_SP | area API | 271 | 2026-01-03 | 2026-07-31 |
| lebanon | VIIRS_SNPP_SP | country archive | 9926 | 2012-01-25 | 2025-12-29 |

## eastmed rows by country (archives)
| source | country | rows |
|---|---|---|
| MODIS_SP | Cyprus | 1372 |
| MODIS_SP | Israel | 3967 |
| MODIS_SP | Lebanon | 2234 |
| MODIS_SP | Palestine | 1070 |
| MODIS_SP | Syria | 39495 |
| MODIS_SP | Turkey | 136112 |
| VIIRS_NOAA20_SP | Cyprus | 3301 |
| VIIRS_NOAA20_SP | Israel | 10508 |
| VIIRS_NOAA20_SP | Lebanon | 5786 |
| VIIRS_NOAA20_SP | Palestine | 4071 |
| VIIRS_NOAA20_SP | Syria | 121946 |
| VIIRS_NOAA20_SP | Turkey | 152729 |
| VIIRS_SNPP_SP | Cyprus | 5557 |
| VIIRS_SNPP_SP | Israel | 19737 |
| VIIRS_SNPP_SP | Lebanon | 9926 |
| VIIRS_SNPP_SP | Palestine | 6032 |
| VIIRS_SNPP_SP | Syria | 190546 |
| VIIRS_SNPP_SP | Turkey | 296414 |

## Archive files not published (404)

- none

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

