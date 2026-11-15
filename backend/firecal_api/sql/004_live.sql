-- Live pipeline: near-real-time detections from NASA FIRMS, kept beside the releases.
--
-- Releases stay immutable. Detections that arrive after a release's last day of data are stored here,
-- turned into fire-days per cell and month, harmonized (firecal_api/live/harmonize.py) and served by the
-- API on top of the current release for the months the release has no data for (`?live=1`).
--
-- `demo` rows include simulated detections (a replayed past outbreak, for demonstrations); they are
-- only served when the client asks for them and never mix into the real rows.

create table live_detection (
    detection_id  text primary key,           -- hash of sensor, time and position: re-sent events are ignored
    sensor        text not null,              -- 'SNPP' | 'NOAA20' | 'NOAA21' | 'SIM'
    source        text not null,              -- FIRMS source id, e.g. 'VIIRS_NOAA20_NRT'
    lat           double precision not null,
    lon           double precision not null,
    acq_at        timestamptz not null,
    day           date not null,              -- UTC day of acq_at: the fire-day
    cell_key      int not null,               -- row * 7200 + col (contract grid)
    confidence    text,                       -- 'l' | 'n' | 'h'
    frp           real,
    daynight      text,
    simulated     boolean not null default false,
    received_at   timestamptz not null default now()
);
create index live_detection_day on live_detection (day, cell_key);
create index live_detection_recent on live_detection (acq_at desc);

-- Mean and sample sd of the release's harmonized values per cell and calendar month (the anomaly baseline).
create table live_cell_baseline (
    release_id  bigint not null references release on delete cascade,
    month       smallint not null check (month between 1 and 12),
    cell_key    int not null,
    mean        double precision not null,
    sd          double precision,
    primary key (release_id, month, cell_key)
);

create table live_region_month (
    region_id          text not null references region on delete cascade,
    ym                 date not null,
    demo               boolean not null,
    release_id         bigint not null,       -- the release the cells and baselines came from
    viirs_raw          int not null,          -- S-NPP fire-days (as the contract's viirs_raw)
    noaa20_raw         int not null default 0,  -- NOAA-20 fire-days of the whole month, uncalibrated
    provisional        boolean not null default false,  -- no calibration or source list for the region
    harmonized         double precision not null,
    harmonized_low     double precision not null,
    harmonized_high    double precision not null,
    anomaly_z          double precision,
    through            date not null,         -- last day covered
    partial_month      boolean not null,
    sensors            jsonb not null,        -- {sensor: fire-days that feed harmonized}
    harmonization      text not null,         -- version of the conversion used
    n_detections       int not null,
    last_detection_at  timestamptz,
    updated_at         timestamptz not null default now(),
    primary key (region_id, ym, demo)
);

-- Only cells with fire-days or a usable baseline have a row; any other cell reads as 0 with no z.
create table live_cell_month (
    region_id        text not null references region on delete cascade,
    ym               date not null,
    demo             boolean not null,
    cell_key         int not null,
    viirs_raw        smallint not null,
    noaa20_raw       smallint not null default 0,
    harmonized       real not null,
    harmonized_low   real not null,
    harmonized_high  real not null,
    anomaly_z        real,
    primary key (region_id, ym, demo, cell_key)
);

-- Small key/value notes of the pipeline (last poll, coverage).
create table live_state (
    key         text primary key,
    value       jsonb not null,
    updated_at  timestamptz not null default now()
);
