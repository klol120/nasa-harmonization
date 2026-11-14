"""Weather context from the Meteomatics API.

Daily past weather is fetched for a few fire hotspots per region, averaged over the hotspots (weighted by
their share of fire-days) and stored as monthly values. The API then serves each month next to its normal
for that calendar month. Nothing is fetched while the website is being used, and nothing here is a forecast.

Credentials (METEOMATICS_USER / METEOMATICS_PASSWORD) are only read on the server and never sent to browsers.
"""

import asyncio
import base64
import calendar
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import asyncpg

from . import contract as C

API_URL = os.environ.get("METEOMATICS_URL", "https://api.meteomatics.com").rstrip("/")
PROVIDER = "Meteomatics"
ATTRIBUTION = "Weather data: Meteomatics (meteomatics.com)"

# column -> (Meteomatics parameter, how the days of a month combine). "_24h" values cover the 24 h before
# their timestamp, so the value at day D+1 00:00Z is day D.
FIELDS: dict[str, tuple[str, str]] = {
    "t_mean_c": ("t_mean_2m_24h:C", "mean"),
    "t_max_c": ("t_max_2m_24h:C", "mean"),
    "precip_mm": ("precip_24h:mm", "sum"),
    "wind_ms": ("wind_speed_mean_10m_24h:ms", "mean"),
    "rh_pct": ("relative_humidity_mean_2m_24h:p", "mean"),
}
LABELS = {
    "t_mean_c": {"label": "Mean temperature", "unit": "°C"},
    "t_max_c": {"label": "Mean daily maximum temperature", "unit": "°C"},
    "precip_mm": {"label": "Precipitation total", "unit": "mm"},
    "wind_ms": {"label": "Mean wind speed (10 m)", "unit": "m/s"},
    "rh_pct": {"label": "Mean relative humidity", "unit": "%"},
}
TILES_PER_SIDE = 3  # the region's bbox is split 3×3; each tile with fires gives one point (≤ 9; the API allows 10)
INVALID = -999  # Meteomatics' "no value"
RECENT_MONTHS = 2  # incomplete months this recent are fetched again (data for the last days may arrive late)
LOCK_KEY = 0x6D657465  # pg advisory lock: one weather fetch at a time per database
LOCK_RETRY_S = 15  # how often a waiting fetch retries the lock


class MeteomaticsError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


class QuotaReached(Exception):
    pass


@dataclass(frozen=True)
class Credentials:
    user: str
    password: str


def credentials() -> Credentials | None:
    user = os.environ.get("METEOMATICS_USER", "").strip()
    password = os.environ.get("METEOMATICS_PASSWORD", "")
    return Credentials(user, password) if user and password else None


def daily_cap() -> int:
    return int(os.environ.get("METEOMATICS_DAILY_CAP", "800"))


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def month_end(m: date) -> date:
    return m.replace(day=calendar.monthrange(m.year, m.month)[1])


def days_in_month(m: date) -> int:
    return calendar.monthrange(m.year, m.month)[1]


# ---------------------------------------------------------------- where to sample


def pick_points(cells: list[dict], bbox: list[float], per_side: int = TILES_PER_SIDE) -> list[dict]:
    """One point per bbox tile that has fires: the tile's busiest cell, weighted by the tile's share of fire-days.

    `cells` are dicts with lat, lon and total (fire-days over the whole record).
    """
    w, s, e, n = bbox
    best: dict[tuple[int, int], dict] = {}
    tile_total: dict[tuple[int, int], float] = {}
    for c in cells:
        if not c["total"] or c["total"] <= 0:
            continue
        i = min(max(int((c["lon"] - w) / (e - w) * per_side), 0), per_side - 1)
        j = min(max(int((c["lat"] - s) / (n - s) * per_side), 0), per_side - 1)
        k = (i, j)
        tile_total[k] = tile_total.get(k, 0.0) + c["total"]
        if k not in best or c["total"] > best[k]["total"]:
            best[k] = c
    tiles = sorted(best, key=lambda k: -tile_total[k])
    total = sum(tile_total[k] for k in tiles)
    return [
        {"lat": round(best[k]["lat"], 4), "lon": round(best[k]["lon"], 4), "weight": round(tile_total[k] / total, 4)}
        for k in tiles
    ]


async def hotspot_cells(conn: asyncpg.Connection, release_id: int) -> list[dict]:
    """Fire-days per cell over the release, leaving out persistent (industrial/waste) sources."""
    rows = await conn.fetch(
        """select c.lat_center lat, c.lon_center lon, sum(cm.harmonized)::float8 total
           from cell_month cm
           join release_cell rc on rc.release_id = cm.release_id and rc.cell_key = cm.cell_key
           join cell c on c.cell_key = cm.cell_key
           where cm.release_id = $1 and not rc.is_persistent
           group by c.cell_key, c.lat_center, c.lon_center
           having sum(cm.harmonized) > 0""",
        release_id,
    )
    return [dict(r) for r in rows]


async def region_points(conn: asyncpg.Connection, release: asyncpg.Record) -> list[dict]:
    """The region's stored points, choosing (and storing) them on first use."""
    region = release["region_id"]
    points = await conn.fetchval("select points from weather_region where region_id = $1", region)
    if points:
        return points
    points = pick_points(await hotspot_cells(conn, release["release_id"]), list(release["bbox"]))
    if not points:
        raise ValueError(f"{region}: no fire-days outside persistent sources, so there is nowhere to sample weather")
    await conn.execute(
        "insert into weather_region (region_id, provider, points) values ($1, $2, $3) on conflict do nothing",
        region, PROVIDER, points,
    )
    return await conn.fetchval("select points from weather_region where region_id = $1", region)


# ---------------------------------------------------------------- the HTTP request


def build_url(points: list[dict], fields: list[str], first_day: date, last_day: date) -> str:
    t0, t1 = first_day + timedelta(days=1), last_day + timedelta(days=1)
    times = f"{t0:%Y-%m-%d}T00:00:00Z" if t0 == t1 else f"{t0:%Y-%m-%d}T00:00:00Z--{t1:%Y-%m-%d}T00:00:00Z:P1D"
    params = ",".join(FIELDS[f][0] for f in fields)
    loc = "+".join(f"{p['lat']:.4f},{p['lon']:.4f}" for p in points)
    return f"{API_URL}/{times}/{params}/{loc}/json"


def http_get(url: str, creds: Credentials, timeout: float = 300) -> dict:
    token = base64.b64encode(f"{creds.user}:{creds.password}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}", "User-Agent": "firecal-backend"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace").strip()
        raise MeteomaticsError(e.code, body[:500] or e.reason) from None


async def take_quota(conn: asyncpg.Connection, cap: int) -> int:
    """Count one request against today's (UTC) cap. Returns today's count; raises QuotaReached at the cap."""
    n = await conn.fetchval(
        """insert into meteomatics_usage as u (day, n) values ((now() at time zone 'utc')::date, 1)
           on conflict (day) do update set n = u.n + 1 where u.n < $1
           returning n""",
        cap,
    )
    if n is None or n > cap:
        raise QuotaReached(f"{cap} Meteomatics requests already sent today (UTC); run again tomorrow")
    return n


async def usage_today(conn: asyncpg.Connection) -> int:
    return await conn.fetchval(
        "select coalesce((select n from meteomatics_usage where day = (now() at time zone 'utc')::date), 0)"
    )


# ---------------------------------------------------------------- response -> monthly values


def parse_daily(body: dict, points: list[dict], fields: list[str]) -> dict[date, dict[str, float]]:
    """{day: {field: value}}, each value the weighted mean over the points that returned one."""
    by_param = {FIELDS[f][0]: f for f in fields}
    acc: dict[date, dict[str, list[float]]] = {}
    for block in body.get("data", []):
        f = by_param.get(block.get("parameter"))
        if f is None:
            continue
        for co in block.get("coordinates", []):
            # Returned coordinates are rounded, so take the nearest requested point.
            p = min(points, key=lambda q: (q["lat"] - co["lat"]) ** 2 + (q["lon"] - co["lon"]) ** 2)
            for d in co.get("dates", []):
                v = d.get("value")
                if v is None or v == INVALID:
                    continue
                day = date.fromisoformat(d["date"][:10]) - timedelta(days=1)
                a = acc.setdefault(day, {}).setdefault(f, [0.0, 0.0])
                a[0] += p["weight"] * v
                a[1] += p["weight"]
    return {day: {f: s / w for f, (s, w) in fs.items() if w > 0} for day, fs in acc.items()}


def to_monthly(daily: dict[date, dict[str, float]], fields: list[str]) -> dict[date, dict]:
    groups: dict[date, list[dict[str, float]]] = {}
    for day, vals in daily.items():
        groups.setdefault(day.replace(day=1), []).append(vals)
    out = {}
    for ym, days in sorted(groups.items()):
        row: dict = {"n_days": sum(1 for d in days if all(f in d for f in fields))}
        for f in fields:
            vs = [d[f] for d in days if f in d]
            row[f] = None if not vs else (sum(vs) if FIELDS[f][1] == "sum" else sum(vs) / len(vs))
        out[ym] = row
    return out


# ---------------------------------------------------------------- what to fetch


def months_to_fetch(first: date, last: date, have: dict[date, int], today: date) -> list[date]:
    """Months with no stored row, plus recent months that have more days available than are stored."""
    yesterday = today - timedelta(days=1)
    recent, m = set(), yesterday.replace(day=1)
    for _ in range(RECENT_MONTHS):
        recent.add(m)
        m = (m - timedelta(days=1)).replace(day=1)
    out = []
    for m in C.month_range(first, min(last, yesterday.replace(day=1))):
        available = (min(month_end(m), yesterday) - m).days + 1
        n = have.get(m)
        if n is None or (n < available and m in recent):
            out.append(m)
    return out


def chunks(months: list[date], size: int) -> list[list[date]]:
    """Runs of consecutive months, at most `size` long."""
    out: list[list[date]] = []
    for m in months:
        cur = out[-1] if out else None
        prev = cur[-1] if cur else None
        nxt = None if prev is None else (date(prev.year + 1, 1, 1) if prev.month == 12 else date(prev.year, prev.month + 1, 1))
        if cur is not None and m == nxt and len(cur) < size:
            cur.append(m)
        else:
            out.append([m])
    return out


# ---------------------------------------------------------------- storing


async def upsert_months(conn: asyncpg.Connection, region: str, rows: dict[date, dict]) -> None:
    cols = list(FIELDS)
    # Fields left out of a fetch keep their stored values.
    sets = ", ".join(f"{c} = coalesce(excluded.{c}, weather_month.{c})" for c in cols)
    await conn.executemany(
        f"""insert into weather_month (region_id, ym, {", ".join(cols)}, n_days, fetched_at)
            values ($1, $2, {", ".join(f"${i + 3}" for i in range(len(cols)))}, ${len(cols) + 3}, now())
            on conflict (region_id, ym) do update set {sets}, n_days = excluded.n_days, fetched_at = now()""",
        [(region, ym, *(r.get(c) for c in cols), r["n_days"]) for ym, r in rows.items()],
    )


# ---------------------------------------------------------------- fetching


async def fetch_region(
    conn: asyncpg.Connection,
    release: asyncpg.Record,
    creds: Credentials | None,
    fields: list[str],
    *,
    chunk_months: int = 12,
    cap: int | None = None,
    dry_run: bool = False,
    today: date | None = None,
    get: Callable[[str, Credentials], dict] = http_get,
    log: Callable[[str], None] = print,
) -> int:
    """Fetch the region's missing months. Returns the number of requests sent (or planned, with dry_run)."""
    region = release["region_id"]
    today = today or utc_today()
    cap = daily_cap() if cap is None else cap
    points = await region_points(conn, release)
    have = {r["ym"]: r["n_days"] for r in await conn.fetch("select ym, n_days from weather_month where region_id = $1", region)}
    todo = months_to_fetch(release["first_month"], release["last_month"], have, today)
    if not todo:
        log(f"[{region}] weather up to date ({len(have)} months stored)")
        return 0
    queue = chunks(todo, chunk_months)
    log(f"[{region}] {len(todo)} months to fetch at {len(points)} points in about {len(queue)} requests")
    if dry_run:
        return len(queue)
    yesterday = today - timedelta(days=1)
    sent = 0
    while queue:
        ch = queue.pop(0)
        first, last = ch[0], min(month_end(ch[-1]), yesterday)
        url = build_url(points, fields, first, last)
        for attempt in range(3):
            await take_quota(conn, cap)
            sent += 1
            try:
                body = await asyncio.to_thread(get, url, creds)
                break
            except MeteomaticsError as e:
                if e.status == 413 and len(ch) > 1:  # too much data in one request: split it
                    half = len(ch) // 2
                    queue[:0] = [ch[:half], ch[half:]]
                    log(f"[{region}] {C.ym_str(ch[0])}..{C.ym_str(ch[-1])} too large, splitting")
                    body = None
                    break
                if e.status >= 500 and attempt < 2:
                    log(f"[{region}] {e}; retrying")
                    await asyncio.sleep(10 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 2:
                    log(f"[{region}] network error ({e}); retrying")
                    await asyncio.sleep(10 * (attempt + 1))
                    continue
                raise
        if body is None:
            continue
        wanted = set(ch)
        rows = {m: r for m, r in to_monthly(parse_daily(body, points, fields), fields).items() if m in wanted}
        await upsert_months(conn, region, rows)
        log(f"[{region}] {C.ym_str(ch[0])}..{C.ym_str(ch[-1])}: stored {len(rows)} months")
    return sent


async def fetch_all(
    conn: asyncpg.Connection,
    regions: list[str] | None,
    creds: Credentials | None,
    fields: list[str],
    log: Callable[[str], None] = print,
    wait_lock: float = 0,
    **kw,
) -> int:
    """Fetch every region's missing months (default: every region with a current release). Returns 0 on success.

    wait_lock: seconds to keep retrying when another fetch holds the lock. During a deploy the new container
    starts while the old one is still fetching; waiting lets the new one carry on once the old one stops.
    """
    deadline = time.monotonic() + wait_lock
    waiting = False
    while not await conn.fetchval("select pg_try_advisory_lock($1)", LOCK_KEY):
        if time.monotonic() >= deadline:
            log("another weather fetch is already running against this database; skipping")
            return 0
        if not waiting:
            log(f"another weather fetch is running; waiting up to {wait_lock:.0f}s for it to finish")
            waiting = True
        await asyncio.sleep(min(LOCK_RETRY_S, max(0.0, deadline - time.monotonic())))
    try:
        rows = await conn.fetch("select * from release where is_current order by region_id")
        if regions:
            unknown = set(regions) - {r["region_id"] for r in rows}
            if unknown:
                log(f"no current release for: {', '.join(sorted(unknown))}")
                return 1
            rows = [r for r in rows if r["region_id"] in regions]
        log(f"Meteomatics requests sent today (UTC, counted here): {await usage_today(conn)}")
        for rel in rows:
            try:
                await fetch_region(conn, rel, creds, fields, log=log, **kw)
            except ValueError as e:
                log(str(e))
        return 0
    except QuotaReached as e:
        log(f"stopped: {e}")
        return 0
    except MeteomaticsError as e:
        log(f"Meteomatics refused the request: {e}{hint(e.status)}")
        return 1
    finally:
        await conn.execute("select pg_advisory_unlock($1)", LOCK_KEY)


def hint(status: int) -> str:
    if status in (401, 402, 403):
        return "\n  check METEOMATICS_USER / METEOMATICS_PASSWORD (the hackathon account ends on 2026-11-22)"
    if status in (400, 404):
        return "\n  a parameter or date may not be in this account's package; try fewer --fields or run weather-check"
    if status == 429:
        return "\n  the account's limit is reached; run again tomorrow"
    return ""


# ---------------------------------------------------------------- serving


def with_anomalies(months: list[dict], baseline: tuple[int, int]) -> list[dict]:
    """Add each field's normal (baseline mean for that calendar month), difference, z and, for rain, % of normal.

    Only complete months count toward normals, and incomplete months get no anomaly.
    """
    import statistics

    clim: dict[tuple[int, str], tuple[float, float | None]] = {}
    for mo in range(1, 13):
        base = [m for m in months if m["ym"].month == mo and m["complete"] and baseline[0] <= m["ym"].year <= baseline[1]]
        for f in FIELDS:
            vs = [m[f] for m in base if m[f] is not None]
            if vs:
                clim[(mo, f)] = (statistics.fmean(vs), statistics.stdev(vs) if len(vs) >= 3 else None)
    out = []
    for m in months:
        row = {"ym": C.ym_str(m["ym"]), "year": m["ym"].year, "month": m["ym"].month,
               "n_days": m["n_days"], "complete": m["complete"]}
        for f in FIELDS:
            v = m[f]
            mean, sd = clim.get((m["ym"].month, f), (None, None))
            anom = v - mean if (v is not None and mean is not None and m["complete"]) else None
            row[f] = r2(v)
            row[f"{f}_normal"] = r2(mean)
            row[f"{f}_anom"] = r2(anom)
            row[f"{f}_z"] = r2(anom / sd) if anom is not None and sd else None
        mean = row["precip_mm_normal"]
        row["precip_pct_of_normal"] = (
            round(100 * m["precip_mm"] / mean) if row["precip_mm_anom"] is not None and mean else None
        )
        out.append(row)
    return out


def r2(v):
    return None if v is None else round(v, 2)


async def region_weather(conn: asyncpg.Connection, region: str, baseline: tuple[int, int],
                         frm: date | None = None, to: date | None = None) -> dict:
    head = {"region": region, "provider": PROVIDER, "attribution": ATTRIBUTION,
            "note": "Past weather at the region's fire hotspots, as context for the fire calendar. Not a forecast.",
            "baseline_years": list(baseline), "fields": LABELS}
    src = await conn.fetchrow("select * from weather_region where region_id = $1", region)
    rows = await conn.fetch("select * from weather_month where region_id = $1 order by ym", region)
    if not src or not rows:
        return {**head, "available": False, "points": [], "months": []}
    months = [{**dict(r), "complete": r["n_days"] == days_in_month(r["ym"])} for r in rows]
    lo, hi = C.ym_str(frm) if frm else "0000-00", C.ym_str(to) if to else "9999-99"
    out = [m for m in with_anomalies(months, baseline) if lo <= m["ym"] <= hi]
    return {**head, "available": True, "points": src["points"],
            "fetched_at": max(r["fetched_at"] for r in rows).isoformat(), "months": out}


# ---------------------------------------------------------------- moving data between deployments


async def export_dir(conn: asyncpg.Connection, folder: Path, log: Callable[[str], None] = print) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    for src in await conn.fetch("select * from weather_region order by region_id"):
        rows = await conn.fetch("select * from weather_month where region_id = $1 order by ym", src["region_id"])
        doc = {
            "provider": src["provider"], "attribution": ATTRIBUTION, "region": src["region_id"],
            "points": src["points"], "fields": LABELS,
            "months": [{"ym": C.ym_str(r["ym"]), **{f: r[f] for f in FIELDS}, "n_days": r["n_days"]} for r in rows],
        }
        path = folder / f"{src['region_id']}.json"
        path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        log(f"wrote {path} ({len(rows)} months)")
    return 0


async def import_dir(conn: asyncpg.Connection, folder: Path, log: Callable[[str], None] = print) -> int:
    """Load <region>.json files written by export_dir. Stored months with more days than the file's are kept."""
    known = {r["region_id"] for r in await conn.fetch("select region_id from region")}
    failed = 0
    for path in sorted(folder.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            region = doc["region"]
            if region not in known:
                log(f"{path.name}: region {region!r} is not loaded; skipped")
                continue
            async with conn.transaction():
                await conn.execute(
                    """insert into weather_region (region_id, provider, points) values ($1, $2, $3)
                       on conflict (region_id) do update set provider = excluded.provider, points = excluded.points""",
                    region, doc.get("provider", PROVIDER), doc["points"],
                )
                cols = list(FIELDS)
                await conn.executemany(
                    f"""insert into weather_month (region_id, ym, {", ".join(cols)}, n_days)
                        values ($1, $2, {", ".join(f"${i + 3}" for i in range(len(cols)))}, ${len(cols) + 3})
                        on conflict (region_id, ym) do update
                        set {", ".join(f"{c} = excluded.{c}" for c in cols)}, n_days = excluded.n_days
                        where excluded.n_days >= weather_month.n_days""",
                    [(region, C.parse_ym(m["ym"]), *(m.get(c) for c in cols), m["n_days"]) for m in doc["months"]],
                )
            log(f"{path.name}: {len(doc['months'])} months for {region}")
        except (KeyError, ValueError, TypeError, C.ContractError) as e:
            failed += 1
            log(f"{path.name}: not a weather export ({e})")
    return 1 if failed else 0


def check(creds: Credentials, lat: float, lon: float, fields: list[str], today: date | None = None) -> dict[str, float | None]:
    """One small request for yesterday at one point, to test the credentials and parameters."""
    day = (today or utc_today()) - timedelta(days=1)
    pts = [{"lat": lat, "lon": lon, "weight": 1.0}]
    t0 = time.monotonic()
    body = http_get(build_url(pts, fields, day, day), creds, timeout=60)
    vals = parse_daily(body, pts, fields).get(day, {})
    return {"day": day.isoformat(), "seconds": round(time.monotonic() - t0, 1), **{f: vals.get(f) for f in fields}}
