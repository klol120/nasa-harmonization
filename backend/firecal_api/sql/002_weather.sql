-- Weather context from Meteomatics: past daily weather at a region's fire hotspots, stored as monthly values.

-- Where the weather is sampled: a few fire hotspots per region, each weighted by its share of fire-days.
-- Chosen once, on the first fetch, so every month uses the same points.
create table weather_region (
    region_id   text primary key references region on delete cascade,
    provider    text not null default 'Meteomatics',
    points      jsonb not null,                -- [{lat, lon, weight}]
    created_at  timestamptz not null default now()
);

create table weather_month (
    region_id   text not null references weather_region on delete cascade,
    ym          date not null,                 -- first day of the month
    t_mean_c    double precision,              -- mean of daily mean 2 m temperature, °C
    t_max_c     double precision,              -- mean of daily max 2 m temperature, °C
    precip_mm   double precision,              -- monthly precipitation total, mm
    wind_ms     double precision,              -- mean of daily mean 10 m wind speed, m/s
    rh_pct      double precision,              -- mean of daily mean 2 m relative humidity, %
    n_days      smallint not null,             -- days with every value present (complete = days in month)
    fetched_at  timestamptz not null default now(),
    primary key (region_id, ym)
);

-- Requests sent to Meteomatics per UTC day, so a fetch stops before the account's daily limit.
create table meteomatics_usage (
    day  date primary key,
    n    int not null
);
