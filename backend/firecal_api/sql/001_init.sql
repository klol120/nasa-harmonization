-- Burning-calendar database, data contract v0.4.
--
-- Every `firecal export` of a region is loaded as a *release*. Releases are immutable; a new export
-- becomes a new release and the region's `is_current` pointer moves to it, so the API never serves a
-- half-loaded export and older releases stay available for comparison (and for reproducing ML runs).
--
-- Cells are keyed internally by cell_key = row * 7200 + col (the contract's global 0.05° grid),
-- which keeps the large cell_month table compact. The contract's string cell_id ("row_col") is kept
-- on `cell` and returned by the API.

create table region (
    region_id   text primary key,              -- folder / meta.region, e.g. 'lebanon'
    created_at  timestamptz not null default now()
);

create table release (
    release_id          bigserial primary key,
    region_id           text not null references region on delete cascade,
    contract_version    text not null,
    generated_at        timestamptz,
    pipeline            jsonb,                 -- {version, config_hash}
    bbox                double precision[] not null,
    countries           text[] not null,
    first_month         date not null,
    last_month          date not null,
    n_cells             int not null,
    n_persistent_cells  int not null,
    baseline_first_year int not null,          -- meta.anomalies.baseline_years
    baseline_last_year  int not null,
    meta                jsonb not null,        -- meta.json exactly as exported
    source_path         text,
    loaded_at           timestamptz not null default now(),
    is_current          boolean not null default false
);
create unique index release_one_current on release (region_id) where is_current;

-- Global 0.05° grid cells. Shared by all regions: the same cell has the same id everywhere.
create table cell (
    cell_key         int primary key,         -- row * 7200 + col
    cell_id          text not null unique,    -- "row_col"
    row              int not null,
    col              int not null,
    lat_center       double precision not null,
    lon_center       double precision not null,
    countries        text[] not null,
    primary_country  text,
    check (cell_key = row * 7200 + col)
);
create index cell_center on cell (lat_center, lon_center);

-- Cells of a release, with the per-region attributes.
create table release_cell (
    release_id     bigint not null references release on delete cascade,
    cell_key       int not null references cell,
    is_persistent  boolean not null,
    primary key (release_id, cell_key)
);

-- region_monthly: region totals and every region-wide flag, one row per month.
create table region_month (
    release_id          bigint not null references release on delete cascade,
    ym                  date not null,         -- first day of the month
    modis_raw           int,
    viirs_raw           int,
    harmonized          double precision,
    harmonized_low      double precision,
    harmonized_high     double precision,
    anomaly_z           double precision,
    is_estimate         boolean not null,
    has_gap             boolean not null,
    data_available      boolean not null,
    partial_month       boolean not null,
    display_only        boolean not null,
    low_confidence      boolean not null,
    n_cells             int not null,
    n_persistent_cells  int not null,
    primary key (release_id, ym)
);

-- calendar: one row per cell per month (the bulk of the data: ~5M rows for eastmed).
create table cell_month (
    release_id       bigint not null references release on delete cascade,
    cell_key         int not null,
    ym               date not null,
    modis_raw        smallint,                 -- MODIS units: never compare with the VIIRS-unit columns
    viirs_raw        smallint,
    harmonized       real,                     -- VIIRS-equivalent fire-days
    harmonized_low   real,
    harmonized_high  real,
    anomaly_z        real,
    primary key (release_id, cell_key, ym)
);
-- Map colouring reads one year for all cells: (release, ym) first.
create index cell_month_by_month on cell_month (release_id, ym);

-- meta.calibration.factors, one row per calendar month (handy as model features).
create table calibration_factor (
    release_id  bigint not null references release on delete cascade,
    model       text not null,                 -- 'level' (meta.calibration.factors) or 'shape' (composite)
    month       smallint not null check (month between 1 and 12),
    a           double precision, a_low double precision, a_high double precision,
    b           double precision, b_low double precision, b_high double precision,
    w_local     double precision,
    primary key (release_id, model, month)
);

-- ---------------------------------------------------------------- machine learning
-- A model run is trained on one release and writes predictions at region and/or cell level.
-- Predictions use the same units as `harmonized` (VIIRS-equivalent fire-days).

create table model_run (
    run_id        bigserial primary key,
    model_name    text not null,               -- e.g. 'seasonal-forecast'
    model_version text not null,
    release_id    bigint not null references release on delete cascade,  -- training data
    target        text not null default 'harmonized',
    params        jsonb not null default '{}',
    metrics       jsonb not null default '{}',
    artifact_uri  text,                        -- where the trained model file lives
    notes         text,
    created_at    timestamptz not null default now()
);
create index model_run_by_release on model_run (release_id, model_name, created_at desc);

create table prediction_region_month (
    run_id      bigint not null references model_run on delete cascade,
    ym          date not null,
    value       double precision not null,
    value_low   double precision,
    value_high  double precision,
    primary key (run_id, ym)
);

create table prediction_cell_month (
    run_id      bigint not null references model_run on delete cascade,
    cell_key    int not null,
    ym          date not null,
    value       real not null,
    value_low   real,
    value_high  real,
    primary key (run_id, cell_key, ym)
);

-- Flat training table for the current release of every region: per-cell values joined with the
-- region-wide flags (the contract keeps those on region_month only) and the cell attributes.
create view ml_cell_month as
select r.region_id,
       c.cell_id, c.cell_key, c.lat_center, c.lon_center, c.primary_country,
       rc.is_persistent,
       cm.ym,
       extract(year from cm.ym)::int  as year,
       extract(month from cm.ym)::int as month,
       cm.modis_raw, cm.viirs_raw, cm.harmonized, cm.harmonized_low, cm.harmonized_high, cm.anomaly_z,
       rm.is_estimate, rm.has_gap, rm.data_available, rm.partial_month, rm.display_only, rm.low_confidence
from release r
join cell_month cm   on cm.release_id = r.release_id
join release_cell rc on rc.release_id = r.release_id and rc.cell_key = cm.cell_key
join cell c          on c.cell_key = cm.cell_key
join region_month rm on rm.release_id = r.release_id and rm.ym = cm.ym
where r.is_current;
