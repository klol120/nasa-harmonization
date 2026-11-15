-- Sparse per-cell storage.
--
-- About 97 % of the calendar rows are cells with no fire that month: every value 0 (or null where the
-- region has no data for that sensor). Only the other rows are stored now, in cell_month_data. The name
-- cell_month becomes a view that puts the zeros back, so every reader sees exactly the rows it saw before:
--
--   a stored row          -> its values, unchanged;
--   a cell-month not stored -> each count 0 where the region has data for it, null where it has none;
--                            harmonized and its band 0 when the month has data, null otherwise;
--                            anomaly_z from cell_zero_z (the z a 0 has for that cell and calendar month).
--
-- A row is left out only when the view rebuilds it exactly, so nothing changes, null or not
-- (sparsify_cells below; ingest.py uses the same function).

create table cell_month_data (
    release_id       bigint not null references release on delete cascade,
    cell_key         int not null,
    ym               date not null,
    modis_raw        smallint,
    viirs_raw        smallint,
    harmonized       real,
    harmonized_low   real,
    harmonized_high  real,
    anomaly_z        real,
    noaa20_raw       smallint,
    primary key (release_id, cell_key, ym)
);
-- One year of every cell of a release (/series) in one contiguous scan.
create index cell_month_data_series on cell_month_data (release_id, ym, cell_key)
    include (harmonized, modis_raw, viirs_raw);

-- The anomaly z of a zero value, per cell and calendar month (it is the same for every zero month).
create table cell_zero_z (
    release_id  bigint not null references release on delete cascade,
    cell_key    int not null,
    month       smallint not null check (month between 1 and 12),
    z           real not null,
    primary key (release_id, cell_key, month)
);

-- Store the rows of one release that the view cannot rebuild, reading them from `src` (a dense table with
-- the columns of cell_month). Returns the number of rows stored.
create function sparsify_cells(src regclass, rid bigint) returns bigint language plpgsql as $fn$
declare
    zero text := $z$
        coalesce(cm.modis_raw, 0) = 0 and (cm.modis_raw is null) = (rm.modis_raw is null)
        and coalesce(cm.viirs_raw, 0) = 0 and (cm.viirs_raw is null) = (rm.viirs_raw is null)
        and coalesce(cm.noaa20_raw, 0) = 0 and (cm.noaa20_raw is null) = (rm.noaa20_raw is null)
        and coalesce(cm.harmonized, 0) = 0 and (cm.harmonized is null) = (not rm.data_available)
        and coalesce(cm.harmonized_low, 0) = 0 and (cm.harmonized_low is null) = (not rm.data_available)
        and coalesce(cm.harmonized_high, 0) = 0 and (cm.harmonized_high is null) = (not rm.data_available)$z$;
    n bigint;
begin
    execute format($q$
        insert into cell_zero_z (release_id, cell_key, month, z)
        select cm.release_id, cm.cell_key, extract(month from cm.ym)::smallint, min(cm.anomaly_z)
        from %s cm join region_month rm on rm.release_id = cm.release_id and rm.ym = cm.ym
        where cm.release_id = $1 and rm.data_available and cm.anomaly_z is not null and %s
        group by 1, 2, 3
        having min(cm.anomaly_z) = max(cm.anomaly_z)$q$, src, zero) using rid;
    execute format($q$
        insert into cell_month_data (release_id, cell_key, ym, modis_raw, viirs_raw, harmonized, harmonized_low,
                                     harmonized_high, anomaly_z, noaa20_raw)
        select cm.release_id, cm.cell_key, cm.ym, cm.modis_raw, cm.viirs_raw, cm.harmonized, cm.harmonized_low,
               cm.harmonized_high, cm.anomaly_z, cm.noaa20_raw
        from %s cm
        join region_month rm on rm.release_id = cm.release_id and rm.ym = cm.ym
        left join cell_zero_z z on z.release_id = cm.release_id and z.cell_key = cm.cell_key
                               and z.month = extract(month from cm.ym)::smallint
        where cm.release_id = $1
          and not (%s and cm.anomaly_z is not distinct from (case when rm.data_available then z.z end))$q$,
        src, zero) using rid;
    get diagnostics n = row_count;
    return n;
end
$fn$;

-- Existing releases.
do $do$
declare r record;
begin
    for r in select release_id from release order by release_id loop
        perform sparsify_cells('cell_month', r.release_id);
    end loop;
end
$do$;

drop view ml_cell_month;
drop table cell_month;

create view cell_month as
select rc.release_id, rc.cell_key, rm.ym,
       case when d.cell_key is not null then d.modis_raw when rm.modis_raw is not null then 0::smallint end as modis_raw,
       case when d.cell_key is not null then d.viirs_raw when rm.viirs_raw is not null then 0::smallint end as viirs_raw,
       case when d.cell_key is not null then d.harmonized when rm.data_available then 0::real end as harmonized,
       case when d.cell_key is not null then d.harmonized_low when rm.data_available then 0::real end as harmonized_low,
       case when d.cell_key is not null then d.harmonized_high when rm.data_available then 0::real end as harmonized_high,
       case when d.cell_key is not null then d.anomaly_z when rm.data_available then z.z end as anomaly_z,
       case when d.cell_key is not null then d.noaa20_raw when rm.noaa20_raw is not null then 0::smallint end as noaa20_raw
from release_cell rc
join region_month rm on rm.release_id = rc.release_id
left join cell_month_data d on d.release_id = rc.release_id and d.cell_key = rc.cell_key and d.ym = rm.ym
left join cell_zero_z z on z.release_id = rc.release_id and z.cell_key = rc.cell_key
                       and z.month = extract(month from rm.ym)::smallint;

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

analyze cell_month_data;
analyze cell_zero_z;
