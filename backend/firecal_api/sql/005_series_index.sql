-- Map colouring reads one year of every cell of a release (/regions/{r}/series/{year}). With the old
-- (release_id, ym) index each of the ~400k rows of a large region was a separate heap read, scattered over
-- the table (rows are loaded cell by cell): minutes per request once the table outgrew memory. This index
-- holds the values too, so the request is one contiguous index-only scan.
create index if not exists cell_month_series on cell_month (release_id, ym, cell_key)
    include (harmonized, modis_raw, viirs_raw);
drop index if exists cell_month_by_month;
