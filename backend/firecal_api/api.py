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

from . import aggregate as A
from . import contract as C
from .config import settings
from .db import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool(settings().database_url)
    app.state.cells = {}  # release_id -> list of cell dicts (releases are immutable)
    app.state.series = OrderedDict()  # (release_id, year) -> encoded JSON
    yield
    await app.state.pool.close()


app = FastAPI(title="Wel3a burning-calendar API", version="0.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(
    CORSMiddleware, allow_origins=settings().cors_origins, allow_methods=["GET", "POST"], allow_headers=["*"]
)

RegionId = Annotated[str, Path(pattern=r"^[a-z0-9_-]{1,64}$")]
ReleaseQ = Annotated[int | None, Query(description="Release id; defaults to the region's current release")]
YmQ = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]


async def conn(request: Request):
    async with request.app.state.pool.acquire() as c:
        yield c


Conn = Annotated[asyncpg.Connection, Depends(conn)]


def jsonr(obj, status: int = 200, cache: bool = False) -> Response:
    headers = {"Cache-Control": "public, max-age=3600"} if cache else {}
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


async def region_cells(request: Request, c: asyncpg.Connection, release_id: int) -> list[dict]:
    cache = request.app.state.cells
    if release_id not in cache:
        rows = await c.fetch(
            """select c.cell_key, c.cell_id, c.row, c.col, c.lat_center, c.lon_center, c.countries, c.primary_country,
                      rc.is_persistent
               from release_cell rc join cell c using (cell_key) where rc.release_id = $1 order by c.cell_key""",
            release_id,
        )
        cache[release_id] = [dict(r) for r in rows]
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


def month_bounds(frm: str | None, to: str | None, rel: asyncpg.Record) -> tuple[date, date]:
    a = C.parse_ym(frm) if frm else rel["first_month"]
    b = C.parse_ym(to) if to else rel["last_month"]
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
    if contract_version == "0.4":
        for f in V05_REGION_MONTH_FIELDS:
            d.pop(f, None)
    return {"ym": C.ym_str(ym), "year": ym.year, "month": ym.month, **d}


@app.get("/regions/{region}/monthly")
async def monthly(region: RegionId, c: Conn, release: ReleaseQ = None, format: Literal["json", "csv"] = "json"):
    """region_monthly: region totals and every region-wide flag, one row per month."""
    r = await release_row(c, region, release)
    rows = [region_month_out(m, r["contract_version"]) for m in await c.fetch(REGION_MONTH_SQL, r["release_id"])]
    if format == "csv":
        buf = io.StringIO()
        fields = [f for f in C.REGION_MONTH_FIELDS if not rows or f in rows[0]]
        w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{region}_region_monthly.csv"'})
    return jsonr(rows, cache=release is not None)


@app.get("/regions/{region}/cells")
async def cells_geojson(region: RegionId, request: Request, c: Conn, release: ReleaseQ = None):
    """cells.geojson: one 0.05° Polygon per cell."""
    r = await release_row(c, region, release)
    d = C.GRID_DEG
    feats = []
    for x in await region_cells(request, c, r["release_id"]):
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
    return jsonr({"type": "FeatureCollection", "features": feats}, cache=release is not None)


@app.get("/regions/{region}/series/{year}")
async def series(region: RegionId, year: int, request: Request, c: Conn, release: ReleaseQ = None):
    """cells_series/{year}.json: compact per-cell monthly values; cells with no fire-days that year are omitted."""
    r = await release_row(c, region, release)
    rid = r["release_id"]
    cache = request.app.state.series
    key = (rid, year)
    if key not in cache:
        months = [m for m in C.month_range(r["first_month"], r["last_month"]) if m.year == year]
        if not months:
            raise HTTPException(404, f"{year} is outside {C.ym_str(r['first_month'])}..{C.ym_str(r['last_month'])}")
        ids = {x["cell_key"]: x["cell_id"] for x in await region_cells(request, c, rid)}
        idx = {m: i for i, m in enumerate(months)}
        out: dict[str, dict] = {}
        cur, h, mo, v = None, None, None, None

        def flush():
            if cur is not None and any(x not in (0, None) for x in (*h, *mo, *v)):
                out[ids[cur]] = {"h": h, "m": mo, "v": v}

        rows = await c.fetch(
            """select cell_key, ym, harmonized, modis_raw, viirs_raw from cell_month
               where release_id = $1 and ym between $2 and $3 order by cell_key, ym""",
            rid, months[0], months[-1],
        )
        for row in rows:
            if row["cell_key"] != cur:
                flush()
                cur = row["cell_key"]
                h, mo, v = [None] * len(months), [None] * len(months), [None] * len(months)
            i = idx[row["ym"]]
            hv = row["harmonized"]
            h[i] = None if hv is None else round(hv, 2)
            mo[i], v[i] = row["modis_raw"], row["viirs_raw"]
        flush()
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
    return Response(cache[key], media_type="application/json", headers={"Cache-Control": "public, max-age=3600"})


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
):
    """calendar rows (cell × month, with bands and z). JSON is capped at 100k rows; CSV streams any size."""
    r = await release_row(c, region, release)
    a, b = month_bounds(frm, to, r)
    rid = r["release_id"]
    cells = await region_cells(request, c, rid)
    ids = {x["cell_key"]: x["cell_id"] for x in cells}
    keys = None
    if cell_id:
        wanted = set(cell_id)
        keys = [k for k, cid in ids.items() if cid in wanted]
        unknown = wanted - {ids[k] for k in keys}
        if unknown:
            raise HTTPException(404, f"cells not in region {region!r}: {sorted(unknown)[:5]}")
    sql = """select cell_key, ym, modis_raw, viirs_raw, noaa20_raw, harmonized, harmonized_low, harmonized_high, anomaly_z
             from cell_month where release_id = $1 and ym between $2 and $3"""
    args: list = [rid, a, b]
    if keys is not None:
        sql += " and cell_key = any($4::int[])"
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


@app.post("/regions/{region}/aggregate")
async def aggregate(region: RegionId, q: AreaQuery, request: Request, c: Conn, release: ReleaseQ = None):
    """Monthly sums over an area, with bands, recomputed anomaly z and the region-wide flags."""
    r = await release_row(c, region, release)
    rid = r["release_id"]
    keys = A.select_cells(
        await region_cells(request, c, rid),
        cell_ids=set(q.cell_ids) if q.cell_ids is not None else None,
        bbox=q.bbox, polygon=q.polygon, exclude_persistent=q.exclude_persistent,
    )
    if not keys:
        raise HTTPException(404, "no cells of this region fall in the requested area")
    months = [dict(m) for m in await c.fetch(REGION_MONTH_SQL, rid)]
    sums = {
        s["ym"]: s
        for s in await c.fetch(
            """select ym, sum(modis_raw)::int modis_raw, sum(viirs_raw)::int viirs_raw, sum(noaa20_raw)::int noaa20_raw,
                      sum(harmonized)::float8 harmonized,
                      sum(harmonized_low)::float8 harmonized_low, sum(harmonized_high)::float8 harmonized_high
               from cell_month where release_id = $1 and cell_key = any($2::int[]) group by ym""",
            rid, keys,
        )
    }
    # z uses the full record (the baseline), whatever window is returned.
    z = A.anomaly_z(months, {ym: s["harmonized"] for ym, s in sums.items()}, (r["baseline_first_year"], r["baseline_last_year"]))
    a, b = month_bounds(q.frm, q.to, r)
    out = []
    for m in months:
        if not a <= m["ym"] <= b:
            continue
        s = sums.get(m["ym"])
        out.append({
            "ym": C.ym_str(m["ym"]), "year": m["ym"].year, "month": m["ym"].month,
            **{f: (r4(s[f]) if s else None) for f in C.ADDITIVE_FIELDS},
            "anomaly_z": r4(z.get(m["ym"])),
            "source": m["source"],
            **{f: m[f] for f in C.REGION_MONTH_FLAGS},
        })
    return jsonr({
        "region": region,
        "release_id": rid,
        "n_cells": len(keys),
        "exclude_persistent": q.exclude_persistent,
        "baseline_years": [r["baseline_first_year"], r["baseline_last_year"]],
        "months": out,
    })


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
