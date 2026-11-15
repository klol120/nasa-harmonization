-- Data contract v0.5: NOAA-20 continuation of VIIRS after S-NPP's end (2026-11-02).
-- region_month.source says what feeds harmonized (MODIS, SNPP, NOAA20, or two joined by '+' for a
-- month split at a switch date). noaa20_raw is uncalibrated NOAA-20 fire-days. Both are null in
-- v0.4 releases.

alter table region_month add column noaa20_raw int, add column source text;
alter table cell_month add column noaa20_raw smallint;

drop view ml_cell_month;
create view ml_cell_month as
select r.region_id,
       c.cell_id, c.cell_key, c.lat_center, c.lon_center, c.primary_country,
       rc.is_persistent,
       cm.ym,
       extract(year from cm.ym)::int  as year,
       extract(month from cm.ym)::int as month,
       cm.modis_raw, cm.viirs_raw, cm.noaa20_raw, cm.harmonized, cm.harmonized_low, cm.harmonized_high, cm.anomaly_z,
       rm.source, rm.is_estimate, rm.has_gap, rm.data_available, rm.partial_month, rm.display_only, rm.low_confidence
from release r
join cell_month cm   on cm.release_id = r.release_id
join release_cell rc on rc.release_id = r.release_id and rc.cell_key = cm.cell_key
join cell c          on c.cell_key = cm.cell_key
join region_month rm on rm.release_id = r.release_id and rm.ym = cm.ym
where r.is_current;
