"""The live tables: storing detections, counting fire-days per cell and month, anomalies and status."""

import calendar
import statistics
from datetime import date, datetime, timedelta, timezone

import asyncpg

from ..contract import month_range, ym_str
from . import harmonize as H

LOCK_KEY = 0x6C697665  # pg advisory lock: one writer of the live tables at a time

# Used in place of `cell_month` to read a release with the live months laid over it.
# Parameters: the caller's, plus region id and demo flag at the positions given to cell_month_live().
_CELL_MONTH_LIVE = """(
    select cm.release_id, cm.cell_key, cm.ym, cm.modis_raw,
           case when lr.ym is null then cm.viirs_raw else coalesce(lc.viirs_raw, 0) end::smallint as viirs_raw,
           case when lr.ym is null then cm.noaa20_raw else coalesce(lc.noaa20_raw, 0) end::smallint as noaa20_raw,
           case when lr.ym is null then cm.harmonized else coalesce(lc.harmonized, 0) end::real as harmonized,
           case when lr.ym is null then cm.harmonized_low else coalesce(lc.harmonized_low, 0) end::real as harmonized_low,
           case when lr.ym is null then cm.harmonized_high else coalesce(lc.harmonized_high, 0) end::real as harmonized_high,
           case when lr.ym is null then cm.anomaly_z else lc.anomaly_z end::real as anomaly_z
    from cell_month cm
    left join live_region_month lr
           on lr.region_id = ${r} and lr.demo = ${d} and lr.ym = cm.ym and lr.release_id = cm.release_id
    left join live_cell_month lc
           on lc.region_id = ${r} and lc.demo = ${d} and lc.ym = cm.ym and lc.cell_key = cm.cell_key and lr.ym is not null
) cm"""


def cell_month_live(region_param: int, demo_param: int) -> str:
    return _CELL_MONTH_LIVE.replace("${r}", f"${region_param}").replace("${d}", f"${demo_param}")


def month_end(ym: date) -> date:
    return ym.replace(day=calendar.monthrange(ym.year, ym.month)[1])


def next_month(ym: date) -> date:
    return date(ym.year + 1, 1, 1) if ym.month == 12 else date(ym.year, ym.month + 1, 1)


def live_first_month(rel) -> date:
    """First month the live pipeline fills for a release: the month holding the day after its last day of
    VIIRS data. A month the release only covers in part is rebuilt whole from the live detections."""
    sources = (rel["meta"] or {}).get("sources") or {}
    days = [v["last_date"] for k, v in sources.items() if k.startswith(("VIIRS_SNPP", "VIIRS_NOAA20")) and v.get("last_date")]
    if not days:
        return next_month(rel["last_month"])
    return (date.fromisoformat(max(days)) + timedelta(days=1)).replace(day=1)


async def current_releases(conn: asyncpg.Connection, regions: list[str] | None = None) -> list[asyncpg.Record]:
    rows = await conn.fetch("select * from release where is_current order by region_id")
    return [r for r in rows if not regions or r["region_id"] in regions]


# ---------------------------------------------------------------- detections


async def known_ids(conn: asyncpg.Connection, ids: list[str]) -> set[str]:
    rows = await conn.fetch("select detection_id from live_detection where detection_id = any($1::text[])", ids)
    return {r["detection_id"] for r in rows}


async def insert_detections(conn: asyncpg.Connection, rows: list[tuple]) -> list[asyncpg.Record]:
    """Insert live_detection rows (see firms.event_row); ones stored already are ignored. Returns the new ones."""
    if not rows:
        return []
    cols = list(zip(*rows))
    return await conn.fetch(
        """insert into live_detection
               (detection_id, sensor, source, lat, lon, acq_at, day, cell_key, confidence, frp, daynight, simulated)
           select * from unnest($1::text[], $2::text[], $3::text[], $4::float8[], $5::float8[], $6::timestamptz[],
                                $7::date[], $8::int[], $9::text[], $10::real[], $11::text[], $12::bool[])
           on conflict (detection_id) do nothing
           returning day, cell_key, simulated""",
        *[list(c) for c in cols],
    )


async def affected(conn: asyncpg.Connection, inserted) -> set[tuple[str, date]]:
    """(region, month) pairs touched by newly stored detections."""
    if not inserted:
        return set()
    rows = await conn.fetch(
        """select distinct r.region_id, date_trunc('month', x.day)::date as ym
           from unnest($1::date[], $2::int[]) x(day, cell_key)
           join release_cell rc on rc.cell_key = x.cell_key
           join release r on r.release_id = rc.release_id and r.is_current""",
        [x["day"] for x in inserted], [x["cell_key"] for x in inserted],
    )
    return {(r["region_id"], r["ym"]) for r in rows}


async def demo_active(conn: asyncpg.Connection) -> bool:
    return bool(await conn.fetchval("select exists(select 1 from live_detection where simulated)"))


async def clear_demo(conn: asyncpg.Connection) -> int:
    """Remove every simulated detection and the demo months built from them."""
    async with conn.transaction():
        n = await conn.fetchval("with d as (delete from live_detection where simulated returning 1) select count(*) from d")
        await conn.execute("delete from live_cell_month where demo")
        await conn.execute("delete from live_region_month where demo")
    return n


# ---------------------------------------------------------------- state


async def get_state(conn: asyncpg.Connection, key: str):
    return await conn.fetchval("select value from live_state where key = $1", key)


async def set_state(conn: asyncpg.Connection, key: str, value) -> None:
    await conn.execute(
        """insert into live_state (key, value) values ($1, $2)
           on conflict (key) do update set value = excluded.value, updated_at = now()""",
        key, value,
    )


async def get_coverage(conn: asyncpg.Connection) -> date | None:
    v = await get_state(conn, "coverage")
    return date.fromisoformat(v["through"]) if v else None


async def advance_coverage(conn: asyncpg.Connection, through: date, **info) -> date:
    """Record that detections are complete up to `through`. Coverage never moves back."""
    old = await get_coverage(conn)
    new = max(old, through) if old else through
    await set_state(conn, "coverage", {"through": new.isoformat(), **info})
    return new


# ---------------------------------------------------------------- months


async def _ensure_baseline(conn: asyncpg.Connection, rel, month: int) -> None:
    rid = rel["release_id"]
    if await conn.fetchval("select 1 from live_cell_baseline where release_id = $1 and month = $2 limit 1", rid, month):
        return
    yms = [date(y, month, 1) for y in range(rel["baseline_first_year"], rel["baseline_last_year"] + 1)]
    async with conn.transaction():
        await conn.execute(
            """insert into live_cell_baseline (release_id, month, cell_key, mean, sd)
               select $1, $2, cm.cell_key, avg(cm.harmonized), stddev_samp(cm.harmonized)
               from cell_month cm join region_month rm on rm.release_id = cm.release_id and rm.ym = cm.ym
               where cm.release_id = $1 and cm.ym = any($3::date[])
                 and rm.data_available and not rm.display_only and cm.harmonized is not null
               group by cm.cell_key having stddev_samp(cm.harmonized) > 0""",
            rid, month, yms,
        )
        # Marker row: the baseline of this month was computed, even if no cell has one.
        await conn.execute("insert into live_cell_baseline (release_id, month, cell_key, mean) values ($1, $2, -1, 0)", rid, month)


async def _region_baseline(conn: asyncpg.Connection, rel, month: int) -> tuple[float, float] | None:
    vals = [
        r["harmonized"]
        for r in await conn.fetch(
            """select harmonized from region_month
               where release_id = $1 and extract(month from ym) = $2 and extract(year from ym) between $3 and $4
                 and data_available and not display_only and harmonized is not null""",
            rel["release_id"], month, rel["baseline_first_year"], rel["baseline_last_year"],
        )
    ]
    if len(vals) < 2:
        return None
    return statistics.fmean(vals), statistics.stdev(vals)  # sample sd, as the contract's region z


def _z(v: float, base) -> float | None:
    return (v - base[0]) / base[1] if base and base[1] and base[1] > 0 else None


async def recompute(conn: asyncpg.Connection, rel, ym: date, *, demo: bool, through: date) -> dict:
    """Rebuild one live month of a region from the stored detections."""
    region, rid = rel["region_id"], rel["release_id"]
    await _ensure_baseline(conn, rel, ym.month)
    rules = H.Rules(region, rel["meta"])
    rows = await conn.fetch(
        """select d.cell_key, d.day, d.sensor, d.confidence, d.simulated, d.lat, d.lon, d.acq_at
           from live_detection d join release_cell rc on rc.release_id = $1 and rc.cell_key = d.cell_key
           where d.day >= $2 and d.day < $3 and d.day <= $5 and (not d.simulated or $4)""",
        rid, ym, next_month(ym), demo, through,
    )
    counts = rules.fire_days((tuple(r)[:7] for r in rows), include_simulated=demo)
    base = {
        r["cell_key"]: (r["mean"], r["sd"])
        for r in await conn.fetch(
            "select cell_key, mean, sd from live_cell_baseline where release_id = $1 and month = $2 and cell_key >= 0",
            rid, ym.month,
        )
    }
    cells, per_sensor = [], {}
    tot_v, tot_n20, tot_h, tot_lo, tot_hi = 0, 0, 0.0, 0.0, 0.0
    for key in counts.keys() | base.keys():
        c = counts.get(key, {})
        # As in the contract: viirs_raw = S-NPP fire-days, noaa20_raw = NOAA-20 fire-days of the whole month.
        v, n20 = c.get("SNPP", 0) + c.get(H.SIM, 0), c.get("NOAA20_all", 0)
        h, lo, hi = rules.to_snpp_equivalent(c, ym.month)
        cells.append((region, ym, demo, key, v, n20, h, lo, hi, _z(h, base.get(key))))
        tot_v, tot_n20, tot_h, tot_lo, tot_hi = tot_v + v, tot_n20 + n20, tot_h + h, tot_lo + lo, tot_hi + hi
        for s, k in c.items():
            if s != "NOAA20_all":
                per_sensor[s] = per_sensor.get(s, 0) + k
    z = _z(tot_h, await _region_baseline(conn, rel, ym.month))
    last = max((r["acq_at"] for r in rows), default=None)
    async with conn.transaction():
        await conn.execute("delete from live_cell_month where region_id = $1 and ym = $2 and demo = $3", region, ym, demo)
        await conn.copy_records_to_table(
            "live_cell_month", records=cells,
            columns=["region_id", "ym", "demo", "cell_key", "viirs_raw", "noaa20_raw", "harmonized", "harmonized_low",
                     "harmonized_high", "anomaly_z"],
        )
        await conn.execute(
            """insert into live_region_month
                   (region_id, ym, demo, release_id, viirs_raw, harmonized, harmonized_low, harmonized_high, anomaly_z,
                    through, partial_month, sensors, harmonization, n_detections, last_detection_at, noaa20_raw, provisional)
               values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
               on conflict (region_id, ym, demo) do update set
                   release_id = excluded.release_id, viirs_raw = excluded.viirs_raw, noaa20_raw = excluded.noaa20_raw,
                   provisional = excluded.provisional, harmonized = excluded.harmonized,
                   harmonized_low = excluded.harmonized_low, harmonized_high = excluded.harmonized_high,
                   anomaly_z = excluded.anomaly_z, through = excluded.through, partial_month = excluded.partial_month,
                   sensors = excluded.sensors, harmonization = excluded.harmonization,
                   n_detections = excluded.n_detections, last_detection_at = excluded.last_detection_at, updated_at = now()""",
            region, ym, demo, rid, tot_v, tot_h, tot_lo, tot_hi, z, through, through < month_end(ym),
            per_sensor, H.VERSION, len(rows), last, tot_n20, rules.provisional,
        )
    return {"region": region, "ym": ym_str(ym), "demo": demo, "fire_days": sum(per_sensor.values()), "harmonized": tot_h,
            "detections": len(rows), "sensors": per_sensor}


async def sync(conn: asyncpg.Connection, dirty: set[tuple[str, date]] | None = None, *, force: bool = False,
               regions: list[str] | None = None) -> list[dict]:
    """Bring the live months up to date: every month from each release's end of data to the covered day.

    A month is rebuilt when it is missing, was touched by new detections (`dirty`), its covered day moved,
    or it was built from another release or another harmonization version. Returns what was rebuilt.
    """
    cov = await get_coverage(conn)
    if cov is None:
        return []
    dirty = dirty or set()
    demo_on = await demo_active(conn)
    if not demo_on:
        await conn.execute("delete from live_cell_month where demo")
        await conn.execute("delete from live_region_month where demo")
    done = []
    for rel in await current_releases(conn, regions):
        region, rid = rel["region_id"], rel["release_id"]
        first = live_first_month(rel)
        last = min(cov.replace(day=1), rel["last_month"])
        months = month_range(first, last) if first <= last else []
        have = {
            (r["ym"], r["demo"]): r
            for r in await conn.fetch("select ym, demo, through, release_id, harmonization from live_region_month where region_id = $1", region)
        }
        for ym in months:
            through = min(month_end(ym), cov)
            for demo in (False, True) if demo_on else (False,):
                row = have.get((ym, demo))
                if (force or row is None or (region, ym) in dirty or row["through"] != through
                        or row["release_id"] != rid or row["harmonization"] != H.VERSION):
                    done.append(await recompute(conn, rel, ym, demo=demo, through=through))
        # Months outside the live window (a newer release now covers them).
        if months:
            for t in ("live_cell_month", "live_region_month"):
                await conn.execute(f"delete from {t} where region_id = $1 and (ym < $2 or ym > $3)", region, months[0], months[-1])
        else:
            for t in ("live_cell_month", "live_region_month"):
                await conn.execute(f"delete from {t} where region_id = $1", region)
    return done


# ---------------------------------------------------------------- reading


async def use_demo(conn: asyncpg.Connection, region: str, demo: bool) -> bool:
    """Demo rows are served only when asked for and present."""
    return demo and bool(await conn.fetchval("select exists(select 1 from live_region_month where region_id = $1 and demo)", region))


async def region_months(conn: asyncpg.Connection, region: str, release_id: int, demo: bool) -> dict[date, asyncpg.Record]:
    rows = await conn.fetch(
        "select * from live_region_month where region_id = $1 and release_id = $2 and demo = $3 order by ym", region, release_id, demo
    )
    return {r["ym"]: r for r in rows}


def overlay_month(m: dict, lv) -> dict:
    """A region_monthly row (ym: date) with a live month laid over it. Adds the `live` fields."""
    if lv is None:
        return m
    return {
        **m,
        "viirs_raw": lv["viirs_raw"], "noaa20_raw": lv["noaa20_raw"], "harmonized": lv["harmonized"],
        "harmonized_low": lv["harmonized_low"], "harmonized_high": lv["harmonized_high"],
        "anomaly_z": None if lv["anomaly_z"] is None else round(lv["anomaly_z"], 4),
        "is_estimate": False, "has_gap": False, "data_available": True, "partial_month": lv["partial_month"],
        "low_confidence": False,
        "live": True, "live_through": lv["through"].isoformat(), "live_sensors": lv["sensors"],
        "source": "+".join(s for s in ("SNPP", "NOAA20") if lv["sensors"].get(s)) or None,
        "live_provisional": lv["provisional"] or lv["harmonization"] != H.VERSION,
    }


async def version(conn: asyncpg.Connection, region: str, demo: bool) -> str | None:
    """Changes whenever the region's live months change (for caches and the client's refresh check)."""
    v = await conn.fetchval("select max(updated_at) from live_region_month where region_id = $1 and demo = $2", region, demo)
    return v.isoformat() if v else None


async def status(conn: asyncpg.Connection, rel, demo: bool, *, points: int = 0, hours: int = 72) -> dict:
    region, rid = rel["region_id"], rel["release_id"]
    months = await region_months(conn, region, rid, demo)
    cov = await get_state(conn, "coverage")
    out = {
        "region": region,
        "enabled": bool(months),
        "demo": demo,
        "demo_available": await demo_active(conn),
        "version": await version(conn, region, demo),
        "through": cov["through"] if cov else None,
        "polled_at": (cov or {}).get("polled_at"),
        "first_month": ym_str(min(months)) if months else None,
        "last_month": ym_str(max(months)) if months else None,
        "last_detection_at": _iso(max((m["last_detection_at"] for m in months.values() if m["last_detection_at"]), default=None)),
        "harmonization": {"version": H.VERSION, "placeholder": any(m["provisional"] for m in months.values())},
        "source": "NASA FIRMS near-real-time VIIRS (S-NPP to 2026-11-02, then NOAA-20 calibrated to S-NPP units)",
        "months": [
            {"ym": ym_str(ym), "fire_days": sum(m["sensors"].values()), "harmonized": m["harmonized"], "through": m["through"].isoformat(),
             "partial_month": m["partial_month"], "sensors": m["sensors"], "detections": m["n_detections"]}
            for ym, m in months.items()
        ],
    }
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    out["detections_24h"] = await conn.fetchval(
        """select count(*) from live_detection d join release_cell rc on rc.release_id = $1 and rc.cell_key = d.cell_key
           where d.received_at >= $2 and (not d.simulated or $3)""",
        rid, since, demo,
    )
    if points:
        rows = await conn.fetch(
            """select d.lat, d.lon, d.acq_at, d.sensor, d.frp, d.simulated
               from live_detection d join release_cell rc on rc.release_id = $1 and rc.cell_key = d.cell_key
               where d.acq_at >= $2 and (not d.simulated or $3) order by d.acq_at desc limit $4""",
            rid, datetime.now(timezone.utc) - timedelta(hours=hours), demo, points,
        )
        out["recent"] = [
            {"lat": r["lat"], "lon": r["lon"], "acq": _iso(r["acq_at"]), "sensor": r["sensor"], "frp": r["frp"], "simulated": r["simulated"]}
            for r in rows
        ]
    return out


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None
