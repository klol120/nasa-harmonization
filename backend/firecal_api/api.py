"""HTTP API over the burning-calendar database.

Every region endpoint serves the region's current release unless `?release=<id>` asks for another,
and returns the contract's shapes, so the frontend can read the same JSON from the API that it would
read from the export files.
"""

import csv
import io
import json
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Literal

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from . import accounts
from . import aggregate as A
from . import chat
from . import contract as C
from . import weather as W
from .config import settings
from .db import create_pool
from .live import store as L


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool(settings().database_url)
    app.state.cells = {}  # release_id -> list of cell dicts (releases are immutable)
    app.state.series = OrderedDict()  # (release_id, year) -> encoded JSON
    app.state.geojson = OrderedDict()  # release_id -> encoded cells.geojson
    yield
    await app.state.pool.close()


app = FastAPI(title="Wel3a burning-calendar API", version="0.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(
    CORSMiddleware, allow_origins=settings().cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["*"],
)

# Accounts, email list, saved areas, plans: optional extras; no data endpoint depends on them.
app.include_router(accounts.router)
# The assistant: off until OPENROUTER_API_KEY is set.
app.include_router(chat.router)

RegionId = Annotated[str, Path(pattern=r"^[a-z0-9_-]{1,64}$")]
ReleaseQ = Annotated[int | None, Query(description="Release id; defaults to the region's current release")]
YmQ = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]
LiveQ = Annotated[bool, Query(description="Lay the live months (near-real-time detections) over the current release")]
DemoQ = Annotated[bool, Query(description="With live: include the simulated demo replay, when one is loaded")]


async def conn(request: Request):
    async with request.app.state.pool.acquire() as c:
        yield c


Conn = Annotated[asyncpg.Connection, Depends(conn)]


# A response for an explicit ?release= never changes (releases are immutable): browsers may keep it.
IMMUTABLE = "public, max-age=31536000, immutable"


def jsonr(obj, status: int = 200, cache: bool = False) -> Response:
    headers = {"Cache-Control": IMMUTABLE} if cache else {}
    return Response(json.dumps(obj, separators=(",", ":"), allow_nan=False), status, headers, media_type="application/json")


def r4(v):
    return None if v is None else round(v, 4)


async def release_row(c: asyncpg.Connection, region: str, release: int | None) -> asyncpg.Record:
    if release is None:
        row = await c.fetchrow("select * from release where region_id = $1 and is_current", region)
    else:
        row = await c.fetchrow("select * from release where region_id = $1 and release_id = $2", region, release)
    if not row:
        raise HTTPException(404, f"no {'current release' if release is None else f'release {release}'} for region {region!r}")
    return row


async def fetch_cells(c: asyncpg.Connection, release_id: int) -> list[dict]:
    rows = await c.fetch(
        """select c.cell_key, c.cell_id, c.row, c.col, c.lat_center, c.lon_center, c.countries, c.primary_country,
                  rc.is_persistent
           from release_cell rc join cell c using (cell_key) where rc.release_id = $1 order by c.cell_key""",
        release_id,
    )
    return [dict(r) for r in rows]


async def region_cells(request: Request, c: asyncpg.Connection, release_id: int) -> list[dict]:
    cache = request.app.state.cells
    if release_id not in cache:
        cache[release_id] = await fetch_cells(c, release_id)
    return cache[release_id]


def release_summary(r: asyncpg.Record) -> dict:
    return {
        "region": r["region_id"],
        "release_id": r["release_id"],
        "is_current": r["is_current"],
        "contract_version": r["contract_version"],
        "generated_at": r["generated_at"].isoformat().replace("+00:00", "Z") if r["generated_at"] else None,
        "loaded_at": r["loaded_at"].isoformat(),
        "bbox": list(r["bbox"]),
        "countries": list(r["countries"]),
        "first_month": C.ym_str(r["first_month"]),
        "last_month": C.ym_str(r["last_month"]),
        "n_cells": r["n_cells"],
        "n_persistent_cells": r["n_persistent_cells"],
        "baseline_years": [r["baseline_first_year"], r["baseline_last_year"]],
    }


async def live_mode(c: asyncpg.Connection, r: asyncpg.Record, live: bool, demo: bool) -> tuple[bool, bool]:
    """(serve live months?, from the demo rows?). Live months only ever sit on top of the current release."""
    on = live and r["is_current"]
    return on, (await L.use_demo(c, r["region_id"], demo) if on else False)


def month_bounds(frm: str | None, to: str | None, rel: asyncpg.Record, last: date | None = None) -> tuple[date, date]:
    a = C.parse_ym(frm) if frm else rel["first_month"]
    b = C.parse_ym(to) if to else (last or rel["last_month"])
    if a > b:
        raise HTTPException(400, "'from' is after 'to'")
    return a, b


# ---------------------------------------------------------------- catalogue


@app.get("/health")
async def health(c: Conn):
    n = await c.fetchval("select count(*) from release where is_current")
    return {"ok": True, "current_releases": n}


@app.get("/regions")
async def regions(c: Conn):
    rows = await c.fetch("select * from release where is_current order by region_id")
    return [release_summary(r) for r in rows]


@app.get("/regions/{region}/releases")
async def releases(region: RegionId, c: Conn):
    rows = await c.fetch("select * from release where region_id = $1 order by release_id desc", region)
    if not rows:
        raise HTTPException(404, f"unknown region {region!r}")
    return [release_summary(r) for r in rows]


@app.get("/regions/{region}/meta")
async def meta(region: RegionId, c: Conn, release: ReleaseQ = None):
    r = await release_row(c, region, release)
    return jsonr({**r["meta"], "release": release_summary(r)}, cache=release is not None)


# ---------------------------------------------------------------- contract files


REGION_MONTH_SQL = """
    select ym, modis_raw, viirs_raw, noaa20_raw, harmonized, harmonized_low, harmonized_high, anomaly_z, source,
           is_estimate, has_gap, data_available, partial_month, display_only, low_confidence, n_cells, n_persistent_cells
    from region_month where release_id = $1 order by ym"""


# Fields added in v0.5; left out of responses for releases loaded from a v0.4 export.
V05_REGION_MONTH_FIELDS = ("noaa20_raw", "source")


def region_month_out(m: asyncpg.Record, contract_version: str) -> dict:
    d = dict(m)
    ym = d.pop("ym")
    if contract_version == "0.4" and not d.get("live"):  # live months carry them on any release
        for f in V05_REGION_MONTH_FIELDS:
            d.pop(f, None)
    return {"ym": C.ym_str(ym), "year": ym.year, "month": ym.month, **d}


async def region_months(c: asyncpg.Connection, r: asyncpg.Record, live: bool, demo: bool) -> list[dict]:
    """region_month rows of a release (ym as date), with the live months laid over them when asked."""
    months = [dict(m) for m in await c.fetch(REGION_MONTH_SQL, r["release_id"])]
    if live:
        lv = await L.region_months(c, r["region_id"], r["release_id"], demo)
        months = [L.overlay_month(m, lv.get(m["ym"])) for m in months]
        months.extend(
            L.overlay_month({
                "ym": ym, "modis_raw": None, "display_only": True,
                "n_cells": r["n_cells"], "n_persistent_cells": r["n_persistent_cells"],
            }, row)
            for ym, row in lv.items() if ym > r["last_month"]
        )
    return months


@app.get("/regions/{region}/monthly")
async def monthly(region: RegionId, c: Conn, release: ReleaseQ = None, format: Literal["json", "csv"] = "json",
                  live: LiveQ = False, demo: DemoQ = False):
    """region_monthly: region totals and every region-wide flag, one row per month.

    With `live=1`, months after the release's last day of data come from the live pipeline; those rows
    carry `live: true`, `live_through`, `live_sensors` and `live_provisional`.
    """
    r = await release_row(c, region, release)
    live, demo = await live_mode(c, r, live, demo)
    rows = [region_month_out(m, r["contract_version"]) for m in await region_months(c, r, live, demo)]
    if format == "csv":
        buf = io.StringIO()
        fields = [f for f in C.REGION_MONTH_FIELDS if not rows or f in rows[0]]
        w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{region}_region_monthly.csv"'})
    return jsonr(rows, cache=release is not None and not live)


@app.get("/regions/{region}/cells")
async def cells_geojson(region: RegionId, request: Request, c: Conn, release: ReleaseQ = None):
    """cells.geojson: one 0.05° Polygon per cell."""
    r = await release_row(c, region, release)
    headers = {"Cache-Control": IMMUTABLE} if release is not None else {}
    cache = request.app.state.geojson
    rid = r["release_id"]
    if rid in cache:
        cache.move_to_end(rid)
        return Response(cache[rid], media_type="application/json", headers=headers)
    d = C.GRID_DEG
    feats = []
    for x in await region_cells(request, c, rid):
        w, s = round(x["col"] * d - 180, 6), round(x["row"] * d - 90, 6)
        e, n = round(w + d, 6), round(s + d, 6)
        feats.append({
            "type": "Feature",
            "properties": {
                "cell_id": x["cell_id"], "row": x["row"], "col": x["col"],
                "lat_center": x["lat_center"], "lon_center": x["lon_center"],
                "countries": list(x["countries"]), "primary_country": x["primary_country"],
                "is_persistent": x["is_persistent"],
            },
            "geometry": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]},
        })
    cache[rid] = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"), allow_nan=False)
    while len(cache) > 24:
        cache.popitem(last=False)
    return Response(cache[rid], media_type="application/json", headers=headers)


@app.get("/regions/{region}/series/{year}")
async def series(region: RegionId, year: int, request: Request, c: Conn, release: ReleaseQ = None,
                 live: LiveQ = False, demo: DemoQ = False):
    """cells_series/{year}.json: compact per-cell monthly values; cells with no fire-days that year are omitted."""
    r = await release_row(c, region, release)
    rid = r["release_id"]
    live, demo = await live_mode(c, r, live, demo)
    # A year holding live months changes as detections arrive: its cache entry is tied to the live version.
    live_version = None
    last_month = r["last_month"]
    if live:
        lv = await L.region_months(c, region, rid, demo)
        if any(m.year == year for m in lv):
            live_version = (demo, max(m["updated_at"] for m in lv.values()))
            last_month = max(last_month, max(lv))
    cache = request.app.state.series
    key = (rid, year, live_version)
    if key not in cache:
        months = [m for m in C.month_range(r["first_month"], last_month) if m.year == year]
        if not months:
            raise HTTPException(404, f"{year} is outside {C.ym_str(r['first_month'])}..{C.ym_str(r['last_month'])}")
        ids = {x["cell_key"]: x["cell_id"] for x in await region_cells(request, c, rid)}
        out = await series_cells(c, rid, months, ids, (region, demo) if live_version else None)
        body = {
            "contract_version": r["contract_version"],
            "year": year,
            "ym": [C.ym_str(m) for m in months],
            "fields": C.SERIES_FIELDS,
            "omitted_cells": "no fire-days this year: 0 where data_available, else null",
            "cells": out,
        }
        cache[key] = json.dumps(body, separators=(",", ":"))
        while len(cache) > 64:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    # A year with live months changes as detections arrive; any other year of a pinned release never does.
    cc = "public, max-age=30" if live_version else IMMUTABLE if release is not None else "public, max-age=3600"
    return Response(cache[key], media_type="application/json", headers={"Cache-Control": cc})


async def series_cells(c: asyncpg.Connection, rid: int, months: list[date], ids: dict[int, str],
                       live: tuple[str, bool] | None) -> dict[str, dict]:
    """Per-cell h/m/v arrays of the given months, for the cells with any fire-day.

    Reads only the stored rows (cell_month_data, and live_cell_month for live months) and fills every other
    value the way the cell_month view would: 0 where the region has data for that field, null where it has
    none. Live months follow the live overlay: harmonized and viirs_raw from the live rows (0 without one),
    modis_raw from the release. Same output as reading the view, without rebuilding every empty cell.
    """
    idx = {m: i for i, m in enumerate(months)}
    n = len(months)
    flags = {
        r["ym"]: r
        for r in await c.fetch(
            """select ym, data_available, modis_raw is null as m_null, viirs_raw is null as v_null
               from region_month where release_id = $1 and ym between $2 and $3""",
            rid, months[0], months[-1],
        )
    }
    live_months: set[date] = set()
    live_rows = []
    if live:
        region, demo = live
        live_months = {
            r["ym"]
            for r in await c.fetch(
                "select ym from live_region_month where region_id = $1 and demo = $2 and release_id = $3 and ym between $4 and $5",
                region, demo, rid, months[0], months[-1],
            )
        }
        if live_months:
            live_rows = await c.fetch(
                """select cell_key, ym, harmonized, viirs_raw from live_cell_month
                   where region_id = $1 and demo = $2 and ym = any($3::date[])""",
                region, demo, list(live_months),
            )
    # Values of a cell-month without a stored row.
    d_h, d_m, d_v = [None] * n, [None] * n, [None] * n
    for m, i in idx.items():
        f = flags.get(m)
        if f is not None:
            d_h[i] = 0.0 if f["data_available"] else None
            d_m[i] = None if f["m_null"] else 0
            d_v[i] = None if f["v_null"] else 0
        if m in live_months:
            d_h[i], d_v[i] = 0.0, 0
    cells: dict[int, list] = {}

    def arrays(key: int) -> list:
        a = cells.get(key)
        if a is None:
            a = cells[key] = [list(d_h), list(d_m), list(d_v)]
        return a

    for row in await c.fetch(
        """select cell_key, ym, harmonized, modis_raw, viirs_raw from cell_month_data
           where release_id = $1 and ym between $2 and $3""",
        rid, months[0], months[-1],
    ):
        if row["cell_key"] not in ids:
            continue
        a, i = arrays(row["cell_key"]), idx[row["ym"]]
        a[1][i] = row["modis_raw"]
        if row["ym"] not in live_months:
            hv = row["harmonized"]
            a[0][i] = None if hv is None else round(hv, 2)
            a[2][i] = row["viirs_raw"]
    for row in live_rows:
        if row["cell_key"] not in ids:
            continue
        a, i = arrays(row["cell_key"]), idx[row["ym"]]
        hv = row["harmonized"]
        a[0][i] = 0.0 if hv is None else round(hv, 2)
        a[2][i] = 0 if row["viirs_raw"] is None else row["viirs_raw"]
    out: dict[str, dict] = {}
    for key in sorted(cells):
        h, mo, v = cells[key]
        if any(x not in (0, None) for x in (*h, *mo, *v)):
            out[ids[key]] = {"h": h, "m": mo, "v": v}
    return out


@app.get("/regions/{region}/calendar")
async def calendar(
    region: RegionId,
    request: Request,
    c: Conn,
    release: ReleaseQ = None,
    cell_id: Annotated[list[str] | None, Query(description="Repeat to select several cells")] = None,
    frm: Annotated[YmQ, Query(alias="from")] = None,
    to: YmQ = None,
    format: Literal["json", "csv"] = "json",
    live: LiveQ = False,
    demo: DemoQ = False,
):
    """calendar rows (cell × month, with bands and z). JSON is capped at 100k rows; CSV streams any size."""
    r = await release_row(c, region, release)
    a, b = month_bounds(frm, to, r)
    rid = r["release_id"]
    live, demo = await live_mode(c, r, live, demo)
    cells = await region_cells(request, c, rid)
    ids = {x["cell_key"]: x["cell_id"] for x in cells}
    keys = None
    if cell_id:
        wanted = set(cell_id)
        keys = [k for k, cid in ids.items() if cid in wanted]
        unknown = wanted - {ids[k] for k in keys}
        if unknown:
            raise HTTPException(404, f"cells not in region {region!r}: {sorted(unknown)[:5]}")
    # $4/$5 are the region and demo flag of the live overlay; only passed with it.
    src = L.cell_month_live(4, 5) if live else "cell_month cm"
    sql = f"""select cell_key, ym, modis_raw, viirs_raw, noaa20_raw, harmonized, harmonized_low, harmonized_high, anomaly_z
              from {src} where release_id = $1 and ym between $2 and $3"""
    args: list = [rid, a, b]
    if live:
        args += [region, demo]
    if keys is not None:
        sql += f" and cell_key = any(${len(args) + 1}::int[])"
        args.append(keys)
    sql += " order by cell_key, ym"

    def out(row) -> dict:
        ym = row["ym"]
        return {
            "cell_id": ids[row["cell_key"]], "ym": C.ym_str(ym), "year": ym.year, "month": ym.month,
            "modis_raw": row["modis_raw"], "viirs_raw": row["viirs_raw"], "noaa20_raw": row["noaa20_raw"],
            "harmonized": r4(row["harmonized"]), "harmonized_low": r4(row["harmonized_low"]),
            "harmonized_high": r4(row["harmonized_high"]), "anomaly_z": r4(row["anomaly_z"]),
        }

    if format == "json":
        n_months = len(C.month_range(a, b))
        if (len(keys) if keys is not None else len(cells)) * n_months > 100_000:
            raise HTTPException(413, "more than 100,000 rows: narrow cell_id/from/to, or use format=csv")
        return jsonr([out(x) for x in await c.fetch(sql, *args)])

    pool = request.app.state.pool

    async def stream():
        # The request's connection is released when the handler returns, so stream on our own.
        async with pool.acquire() as sc, sc.transaction():
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=C.CALENDAR_FIELDS, lineterminator="\n")
            w.writeheader()
            async for row in sc.cursor(sql, *args, prefetch=5000):
                w.writerow(out(row))
                if buf.tell() > 1 << 16:
                    yield buf.getvalue()
                    buf.seek(0)
                    buf.truncate()
            yield buf.getvalue()

    return StreamingResponse(stream(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{region}_calendar.csv"'})


# ---------------------------------------------------------------- area aggregation


class AreaQuery(BaseModel):
    """Cells are selected by every filter given; with none, the whole region is used."""

    cell_ids: list[str] | None = Field(None, description="Explicit cell ids")
    bbox: list[float] | None = Field(None, min_length=4, max_length=4, description="[west, south, east, north]")
    polygon: list[list[list[float]]] | None = Field(None, description="GeoJSON Polygon coordinates: [outer, *holes]")
    exclude_persistent: bool = Field(False, description="Drop cells with persistent industrial/waste-burning sources")
    frm: str | None = Field(None, alias="from", pattern=r"^\d{4}-\d{2}$")
    to: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _check(self):
        if self.polygon is not None and (not self.polygon or len(self.polygon[0]) < 4):
            raise ValueError("polygon needs an outer ring of at least 4 positions")
        return self


async def area_sums(c: asyncpg.Connection, rid: int, keys: list[int], months: list[dict],
                    live: tuple[str, bool] | None) -> dict[date, dict]:
    """Per month, the additive fields summed over the cells `keys`, as summing the cell_month view would.

    Reads only the stored rows. A cell-month without one adds 0 where the region has data for that field and
    nothing where it has none, so a sum is null only when every selected cell is null. Live months (rows of
    `months` marked live) follow the live overlay: harmonized, bands, viirs_raw and noaa20_raw are the sums of
    the live rows (0 without one), modis_raw comes from the release.
    """
    n_sel = len(keys)
    stored = {
        r["ym"]: r
        for r in await c.fetch(
            """select ym, count(*) n,
                      sum(modis_raw) modis_raw, count(modis_raw) n_modis_raw,
                      sum(viirs_raw) viirs_raw, count(viirs_raw) n_viirs_raw,
                      sum(noaa20_raw) noaa20_raw, count(noaa20_raw) n_noaa20_raw,
                      sum(harmonized::float8) harmonized, count(harmonized) n_harmonized,
                      sum(harmonized_low::float8) harmonized_low, count(harmonized_low) n_harmonized_low,
                      sum(harmonized_high::float8) harmonized_high, count(harmonized_high) n_harmonized_high
               from cell_month_data where release_id = $1 and cell_key = any($2::int[]) group by ym""",
            rid, keys,
        )
    }
    live_ym = [m["ym"] for m in months if m.get("live")]
    live_sums = {}
    if live and live_ym:
        live_sums = {
            r["ym"]: r
            for r in await c.fetch(
                """select ym, sum(viirs_raw) viirs_raw, sum(noaa20_raw) noaa20_raw, sum(harmonized::float8) harmonized,
                          sum(harmonized_low::float8) harmonized_low, sum(harmonized_high::float8) harmonized_high
                   from live_cell_month where region_id = $1 and demo = $2 and ym = any($3::date[])
                     and cell_key = any($4::int[]) group by ym""",
                live[0], live[1], live_ym, keys,
            )
        }
    live_fields = ("viirs_raw", "noaa20_raw", "harmonized", "harmonized_low", "harmonized_high")
    out = {}
    for m in months:
        ym, st = m["ym"], stored.get(m["ym"])
        unstored = n_sel - (st["n"] if st else 0)
        row = {}
        for f in C.ADDITIVE_FIELDS:
            if m.get("live") and f in live_fields:
                v = (live_sums.get(ym) or {}).get(f)
                row[f] = (0 if f in ("viirs_raw", "noaa20_raw") else 0.0) if v is None else v
                continue
            default_null = (not m["data_available"]) if f.startswith("harmonized") else m[f] is None
            if st and st["n_" + f]:
                row[f] = st[f]
            elif unstored and not default_null:
                row[f] = 0.0 if f.startswith("harmonized") else 0
            else:
                row[f] = None
        out[ym] = row
    return out


async def area_months(
    c: asyncpg.Connection, r: asyncpg.Record, cells: list[dict], *,
    cell_ids: set[str] | None = None, bbox=None, polygon=None, exclude_persistent: bool = False,
    live: bool = False, demo: bool = False,
) -> tuple[list[int], list[dict]]:
    """Every month of the release summed over an area: (cell keys, rows in the aggregate endpoint's shape).

    Raises 404 when no cell of the region falls in the area. Shared by /aggregate and the saved-area
    features (status badges, alerts).
    """
    rid = r["release_id"]
    keys = A.select_cells(cells, cell_ids=cell_ids, bbox=bbox, polygon=polygon, exclude_persistent=exclude_persistent)
    if not keys:
        raise HTTPException(404, "no cells of this region fall in the requested area")
    months = await region_months(c, r, live, demo)
    sums = await area_sums(c, rid, keys, months, (r["region_id"], demo) if live else None)
    # z uses the full record (the baseline), whatever window is returned.
    z = A.anomaly_z(months, {ym: s["harmonized"] for ym, s in sums.items()}, (r["baseline_first_year"], r["baseline_last_year"]))
    out = []
    for m in months:
        s = sums.get(m["ym"])
        out.append({
            "ym": C.ym_str(m["ym"]), "year": m["ym"].year, "month": m["ym"].month,
            **{f: (r4(s[f]) if s else None) for f in C.ADDITIVE_FIELDS},
            "anomaly_z": r4(z.get(m["ym"])),
            "source": m["source"],
            **{f: m[f] for f in C.REGION_MONTH_FLAGS},
            **{f: m[f] for f in ("live", "live_through", "live_provisional") if f in m},
        })
    return keys, out


@app.post("/regions/{region}/aggregate")
async def aggregate(region: RegionId, q: AreaQuery, request: Request, c: Conn, release: ReleaseQ = None,
                    live: LiveQ = False, demo: DemoQ = False):
    """Monthly sums over an area, with bands, recomputed anomaly z and the region-wide flags."""
    r = await release_row(c, region, release)
    rid = r["release_id"]
    live, demo = await live_mode(c, r, live, demo)
    keys, months = await area_months(
        c, r, await region_cells(request, c, rid),
        cell_ids=set(q.cell_ids) if q.cell_ids is not None else None,
        bbox=q.bbox, polygon=q.polygon, exclude_persistent=q.exclude_persistent, live=live, demo=demo,
    )
    a, b = month_bounds(q.frm, q.to, r, C.parse_ym(months[-1]["ym"]) if live and months else None)
    out = [m for m in months if C.ym_str(a) <= m["ym"] <= C.ym_str(b)]
    return jsonr({
        "region": region,
        "release_id": rid,
        "n_cells": len(keys),
        "exclude_persistent": q.exclude_persistent,
        "baseline_years": [r["baseline_first_year"], r["baseline_last_year"]],
        "months": out,
    })


# ---------------------------------------------------------------- live pipeline


@app.get("/regions/{region}/live")
async def live_status(region: RegionId, c: Conn, demo: DemoQ = False,
                      points: Annotated[int, Query(ge=0, le=5000, description="Also return this many of the latest detections")] = 0,
                      hours: Annotated[int, Query(ge=1, le=24 * 31)] = 72):
    """What the live pipeline holds for the region: the months it fills, how fresh they are, and `version`,
    which changes whenever those months change (clients poll it and reload when it moves)."""
    r = await release_row(c, region, None)
    return jsonr(await L.status(c, r, await L.use_demo(c, region, demo), points=points, hours=hours))


# ---------------------------------------------------------------- weather context


@app.get("/regions/{region}/weather")
async def weather(region: RegionId, c: Conn, frm: Annotated[YmQ, Query(alias="from")] = None, to: YmQ = None):
    """Monthly past weather at the region's fire hotspots (Meteomatics), with each month's normal and anomaly.

    Served from the database only: `available` is false until `firecal-db weather-fetch` has run.
    Normals use the current release's baseline years.
    """
    r = await release_row(c, region, None)
    body = await W.region_weather(
        c, region, (r["baseline_first_year"], r["baseline_last_year"]),
        C.parse_ym(frm) if frm else None, C.parse_ym(to) if to else None,
    )
    return jsonr(body)


# ---------------------------------------------------------------- model predictions


@app.get("/regions/{region}/model-runs")
async def model_runs(region: RegionId, c: Conn):
    rows = await c.fetch(
        """select m.*, r.is_current from model_run m join release r using (release_id)
           where r.region_id = $1 order by m.created_at desc""",
        region,
    )
    return [
        {**{k: v for k, v in dict(x).items() if k != "created_at"}, "created_at": x["created_at"].isoformat()}
        for x in rows
    ]


@app.get("/regions/{region}/predictions")
async def predictions(
    region: RegionId,
    request: Request,
    c: Conn,
    run_id: int | None = None,
    model_name: str | None = None,
    level: Literal["region", "cell"] = "region",
    frm: Annotated[YmQ, Query(alias="from")] = None,
    to: YmQ = None,
):
    """Predictions of one model run (default: the latest run trained on the current release)."""
    if run_id is None:
        run = await c.fetchrow(
            """select m.* from model_run m join release r using (release_id)
               where r.region_id = $1 and r.is_current and ($2::text is null or m.model_name = $2)
               order by m.created_at desc limit 1""",
            region, model_name,
        )
    else:
        run = await c.fetchrow(
            "select m.* from model_run m join release r using (release_id) where r.region_id = $1 and m.run_id = $2",
            region, run_id,
        )
    if not run:
        raise HTTPException(404, "no matching model run")
    a = C.parse_ym(frm) if frm else date(1, 1, 1)
    b = C.parse_ym(to) if to else date(9999, 12, 1)
    head = {"run_id": run["run_id"], "model_name": run["model_name"], "model_version": run["model_version"],
            "release_id": run["release_id"], "target": run["target"], "level": level}
    if level == "region":
        rows = await c.fetch(
            "select * from prediction_region_month where run_id = $1 and ym between $2 and $3 order by ym", run["run_id"], a, b
        )
        return jsonr({**head, "months": [
            {"ym": C.ym_str(x["ym"]), "value": r4(x["value"]), "value_low": r4(x["value_low"]), "value_high": r4(x["value_high"])}
            for x in rows]})
    ids = {x["cell_key"]: x["cell_id"] for x in await region_cells(request, c, run["release_id"])}
    rows = await c.fetch(
        "select * from prediction_cell_month where run_id = $1 and ym between $2 and $3 order by cell_key, ym",
        run["run_id"], a, b,
    )
    return jsonr({**head, "rows": [
        {"cell_id": ids.get(x["cell_key"], f"{x['cell_key'] // C.GRID_COLS}_{x['cell_key'] % C.GRID_COLS}"),
         "ym": C.ym_str(x["ym"]), "value": r4(x["value"]), "value_low": r4(x["value_low"]), "value_high": r4(x["value_high"])}
        for x in rows]})
