"""Load one `firecal export` region folder into the database as a new release.

Everything happens in one transaction: either the whole export is loaded and checked against the
contract invariants, and becomes the region's current release, or nothing changes.

The calendar is read from calendar.parquet (full float32 precision) through DuckDB and streamed into
PostgreSQL with COPY; calendar.csv.gz is the fallback, but its values are rounded to 3 decimals, so
exact halves such as 0.125 can no longer be rounded the way the series files were. pandas/pyarrow are
not used: this machine's Application Control policy blocks them.
"""

import contextlib
import gzip
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import asyncpg

from . import contract as C
from .contract import ContractError

REQUIRED_FILES = ("meta.json", "region_monthly.json", "cells.geojson")
CALENDAR_FILES = ("calendar.parquet", "calendar.csv.gz")  # in order of preference; one is required


def export_fingerprint(folder: Path, calendar_name: str) -> str:
    """Identify the exact metadata, region months, cells, and calendar used."""
    digest = hashlib.sha256()
    for name in (*REQUIRED_FILES, calendar_name):
        with (folder / name).open("rb") as f:
            digest.update(name.encode("utf-8") + b"\0")
            digest.update(hashlib.file_digest(f, "sha256").digest())
    return digest.hexdigest()


def calendar_input(folder: Path, warnings: list[str]) -> Path:
    parquet, csv = (folder / name for name in CALENDAR_FILES)
    if parquet.is_file():
        try:
            import duckdb
        except ImportError:
            if csv.is_file():
                warnings.append("duckdb is not installed: loading calendar.csv.gz, whose values are rounded to 3 decimals")
        else:
            return parquet
    if csv.is_file():
        return csv
    raise ContractError(f"{folder}: no readable calendar ({' or '.join(CALENDAR_FILES)})")


@contextlib.contextmanager
def calendar_csv(source: Path):
    """Yield (path, opener) for the selected calendar source."""
    if source.suffix == ".gz":
        yield source, lambda p, mode: gzip.open(p, mode, **({"encoding": "utf-8", "newline": ""} if "t" in mode else {}))
        return

    import duckdb

    fd, tmp = tempfile.mkstemp(suffix=".csv", prefix="firecal_calendar_")
    os.close(fd)
    try:
        src, dst = str(source).replace("'", "''"), tmp.replace("'", "''")
        con = duckdb.connect()
        try:
            con.execute(f"copy (select * from read_parquet('{src}')) to '{dst}' (header, delimiter ',')")
        finally:
            con.close()
        yield Path(tmp), lambda p, mode: open(p, mode, **({"encoding": "utf-8", "newline": ""} if "t" in mode else {}))
    finally:
        os.unlink(tmp)


@dataclass
class IngestReport:
    region: str
    release_id: int | None = None
    n_cells: int = 0
    n_months: int = 0
    n_cell_months: int = 0
    n_series_files: int = 0
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0


def _load_json(p: Path):
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _unknown(rows: list[dict], known: tuple[str, ...], what: str, warnings: list[str]) -> None:
    extra = sorted({k for r in rows[:50] for k in r} - set(known))
    if extra:
        warnings.append(f"{what}: ignoring fields not in the contract: {', '.join(extra)}")


# ---------------------------------------------------------------- file-level checks (no database)


def read_meta(folder: Path, warnings: list[str]) -> dict:
    for name in REQUIRED_FILES:
        if not (folder / name).is_file():
            raise ContractError(f"{folder}: missing required file {name}")
    if not any((folder / n).is_file() for n in CALENDAR_FILES):
        raise ContractError(f"{folder}: missing calendar ({' or '.join(CALENDAR_FILES)})")
    meta = _load_json(folder / "meta.json")
    C.check_version(meta.get("contract_version"), f"{folder.name}/meta.json")
    for k in ("region", "bbox", "countries", "n_cells", "n_persistent_cells", "time", "anomalies"):
        if k not in meta:
            raise ContractError(f"meta.json: missing {k!r}")
    if meta["region"] != folder.name:
        warnings.append(f"folder is {folder.name!r} but meta.region is {meta['region']!r}; using meta.region")
    for path, size in (meta.get("files") or {}).items():
        p = folder / path
        if not p.is_file():
            warnings.append(f"meta.files lists {path}, which is not in the folder")
        elif p.stat().st_size != size:
            warnings.append(f"{path}: {p.stat().st_size} bytes on disk, meta.files says {size}")
    return meta


def parse_region_monthly(folder: Path, meta: dict, warnings: list[str]) -> list[tuple]:
    rows = _load_json(folder / "region_monthly.json")
    _unknown(rows, C.REGION_MONTH_FIELDS, "region_monthly", warnings)
    first = C.parse_ym(meta["time"]["first_month"])
    last = C.parse_ym(meta["time"]["last_month"])
    expected = C.month_range(first, last)
    got = [C.parse_ym(r["ym"]) for r in rows]
    if got != expected:
        raise ContractError(
            f"region_monthly must have one row per month from {C.ym_str(first)} to {C.ym_str(last)} "
            f"in order ({len(got)} rows, {len(expected)} expected)"
        )
    out, errors = [], []
    for r, ym in zip(rows, got):
        where = f"region_monthly {r['ym']}"
        if (r["year"], r["month"]) != (ym.year, ym.month):
            errors.append(f"{where}: year/month disagree with ym")
        for f in C.REGION_MONTH_FLAGS:
            if not isinstance(r.get(f), bool):
                errors.append(f"{where}: {f} must be true/false")
        h, lo, hi = r.get("harmonized"), r.get("harmonized_low"), r.get("harmonized_high")
        if (h is None) == bool(r.get("data_available")):
            errors.append(f"{where}: harmonized must be null iff data_available is false")
        if h is not None and (lo is None or hi is None or not lo - 1e-6 <= h <= hi + 1e-6):
            errors.append(f"{where}: need harmonized_low <= harmonized <= harmonized_high")
        # v0.5: source says what feeds harmonized, null iff there is no data (absent in v0.4).
        if "source" in r and (r["source"] is None) == bool(r.get("data_available")):
            errors.append(f"{where}: source must be null iff data_available is false")
        out.append((
            ym, r.get("modis_raw"), r.get("viirs_raw"), r.get("noaa20_raw"), h, lo, hi, r.get("anomaly_z"), r.get("source"),
            *(r[f] for f in C.REGION_MONTH_FLAGS), r["n_cells"], r["n_persistent_cells"],
        ))
    if errors:
        raise ContractError(_summary(errors))
    return out


def parse_cells(folder: Path, meta: dict) -> tuple[list[tuple], list[tuple]]:
    """Returns (cell rows, (cell_key, is_persistent) rows)."""
    fc = _load_json(folder / "cells.geojson")
    cells, members, errors = [], [], []
    tol = 1e-6
    for f in fc.get("features", []):
        p = f["properties"]
        row, col, cid = p["row"], p["col"], p["cell_id"]
        if cid != C.cell_id(row, col):
            errors.append(f"cell {cid}: cell_id is not row_col ({row}_{col})")
        if C.cell_rc(p["lat_center"], p["lon_center"]) != (row, col):
            errors.append(f"cell {cid}: centre ({p['lat_center']}, {p['lon_center']}) is not in row {row}, col {col}")
        ring = f["geometry"]["coordinates"][0] if f["geometry"]["type"] == "Polygon" else []
        w, s = col * C.GRID_DEG - 180, row * C.GRID_DEG - 90
        xs, ys = [x for x, _ in ring], [y for _, y in ring]
        if not ring or abs(min(xs) - w) > tol or abs(max(xs) - w - C.GRID_DEG) > tol or abs(min(ys) - s) > tol or abs(max(ys) - s - C.GRID_DEG) > tol:
            errors.append(f"cell {cid}: geometry is not its 0.05° square")
        key = C.cell_key(row, col)
        cells.append((key, cid, row, col, p["lat_center"], p["lon_center"], list(p.get("countries") or []), p.get("primary_country")))
        members.append((key, bool(p["is_persistent"])))
    if len({c[0] for c in cells}) != len(cells):
        errors.append("cells.geojson has duplicate cells")
    if len(cells) != meta["n_cells"]:
        errors.append(f"cells.geojson has {len(cells)} cells, meta.n_cells says {meta['n_cells']}")
    n_pers = sum(m[1] for m in members)
    if n_pers != meta["n_persistent_cells"]:
        errors.append(f"cells.geojson has {n_pers} persistent cells, meta says {meta['n_persistent_cells']}")
    if errors:
        raise ContractError(_summary(errors))
    return cells, members


def parse_series(folder: Path, meta: dict) -> tuple[list[tuple], dict[int, list]]:
    """Rows (cell_key, ym, h, m, v) of every cells_series file, and the cells listed per year."""
    rows, listed = [], {}
    sdir = folder / "cells_series"
    if not sdir.is_dir():
        return rows, listed
    for p in sorted(sdir.glob("*.json")):
        d = _load_json(p)
        C.check_version(d.get("contract_version"), f"cells_series/{p.name}")
        yms = [C.parse_ym(s) for s in d["ym"]]
        if any(ym.year != d["year"] for ym in yms):
            raise ContractError(f"cells_series/{p.name}: ym entries outside year {d['year']}")
        fields = d.get("fields", C.SERIES_FIELDS)
        if fields != C.SERIES_FIELDS:
            raise ContractError(f"cells_series/{p.name}: unexpected fields {fields}")
        keys = []
        for cid, s in d["cells"].items():
            key = C.cell_key(*C.parse_cell_id(cid))
            keys.append(key)
            if not all(len(s[k]) == len(yms) for k in ("h", "m", "v")):
                raise ContractError(f"cells_series/{p.name}: arrays of {cid} are not aligned with ym")
            for i, ym in enumerate(yms):
                rows.append((key, ym, s["h"][i], s["m"][i], s["v"][i]))
        listed[d["year"]] = keys
    return rows, listed


def _summary(errors: list[str], limit: int = 8) -> str:
    more = f"\n  … and {len(errors) - limit} more" if len(errors) > limit else ""
    return f"{len(errors)} contract violation(s):\n  " + "\n  ".join(errors[:limit]) + more


# ---------------------------------------------------------------- database load


async def _check(conn, sql: str, label: str, *args) -> list[str]:
    """Run a query returning offending rows; turn them into messages."""
    bad = await conn.fetch(sql + " limit 6", *args)
    return [f"{label}: {dict(r)}" for r in bad]


async def ingest_region(
    conn: asyncpg.Connection,
    folder: Path,
    *,
    check_series: bool = True,
    make_current: bool = True,
    force: bool = False,
    log=print,
) -> IngestReport:
    t0 = time.perf_counter()
    folder = folder.resolve()
    warnings: list[str] = []
    source = calendar_input(folder, warnings)
    fingerprint = export_fingerprint(folder, source.name)
    meta = read_meta(folder, warnings)
    region = meta["region"]
    rep = IngestReport(region=region, warnings=warnings)
    generated_at = datetime.fromisoformat(meta["generated_at"].replace("Z", "+00:00")) if meta.get("generated_at") else None
    if not force:
        prev = await conn.fetchval(
            """select release_id from release where region_id = $1 and export_fingerprint = $2
               order by is_current desc, release_id desc limit 1""",
            region, fingerprint,
        )
        if prev:
            log(f"[{region}] this export (generated {meta['generated_at']}) is already release {prev}; skipping (use --force to reload)")
            rep.release_id, rep.skipped = prev, True
            return rep

    log(f"[{region}] reading region_monthly, cells{', series' if check_series else ''}...")
    months = parse_region_monthly(folder, meta, warnings)
    cells, members = parse_cells(folder, meta)
    series, listed = parse_series(folder, meta) if check_series else ([], {})
    first, last = months[0][0], months[-1][0]
    b0, b1 = meta["anomalies"]["baseline_years"]

    async with conn.transaction():
        await conn.execute("insert into region (region_id) values ($1) on conflict do nothing", region)
        release_id = await conn.fetchval(
            """insert into release (region_id, contract_version, generated_at, pipeline, bbox, countries,
                   first_month, last_month, n_cells, n_persistent_cells, baseline_first_year, baseline_last_year,
                   meta, source_path, export_fingerprint)
               values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15) returning release_id""",
            region, meta["contract_version"], generated_at, meta.get("pipeline"), meta["bbox"], meta["countries"],
            first, last, meta["n_cells"], meta["n_persistent_cells"], b0, b1, meta, str(folder), fingerprint,
        )
        rep.release_id = release_id
        log(f"[{region}] release {release_id}: loading {len(cells)} cells and {len(months)} months")

        # Cells are global: upsert, so a cell shared with another region keeps one row.
        await conn.execute(
            "create temp table _cell (like cell including defaults) on commit drop"
        )
        await conn.copy_records_to_table("_cell", records=cells)
        await conn.execute(
            """insert into cell select * from _cell
               on conflict (cell_key) do update set countries = excluded.countries, primary_country = excluded.primary_country"""
        )
        await conn.copy_records_to_table(
            "release_cell", records=[(release_id, k, p) for k, p in members], columns=["release_id", "cell_key", "is_persistent"]
        )
        await conn.copy_records_to_table(
            "region_month",
            records=[(release_id, *m) for m in months],
            columns=["release_id", "ym", "modis_raw", "viirs_raw", "noaa20_raw", "harmonized", "harmonized_low",
                     "harmonized_high", "anomaly_z", "source", *C.REGION_MONTH_FLAGS, "n_cells", "n_persistent_cells"],
        )

        # Calendar: stream a CSV into a text staging table whose columns follow the file header
        # (so added fields are tolerated), then cast into cell_month.
        log(f"[{region}] copying the calendar...")
        with calendar_csv(source) as (cal, opener):
            with opener(cal, "rt") as f:
                header = f.readline().strip().split(",")
            missing = [c for c in C.CALENDAR_FIELDS if c not in header and c not in C.OPTIONAL_CALENDAR_FIELDS]
            if missing:
                raise ContractError(f"calendar: missing columns {missing}")
            extra = [c for c in header if c not in C.CALENDAR_FIELDS]
            if extra:
                warnings.append(f"calendar: ignoring fields not in the contract: {', '.join(extra)}")
            cols = ", ".join(f'"{c}" text' for c in header)
            await conn.execute(f"create temp table _cal ({cols}) on commit drop")
            with opener(cal, "rb") as f:
                await conn.copy_to_table("_cal", source=f, format="csv", header=True)

        errors = await _check(conn, """
            select cell_id, ym, year, month from _cal
            where ym !~ '^\\d{4}-\\d{2}$' or cell_id !~ '^\\d+_\\d+$'
               or year::int <> left(ym, 4)::int or month::int <> right(ym, 2)::int""", "bad cell_id/ym/year/month")
        if errors:
            raise ContractError(_summary(errors))
        # The calendar is loaded and checked as a dense temporary table; afterwards only the rows the
        # cell_month view cannot rebuild (cells with fire, mostly) are stored (sql/007_sparse_cells.sql).
        await conn.execute(
            "create temp table _dense (like cell_month_data including defaults, primary key (release_id, cell_key, ym)) on commit drop"
        )
        try:
            n = await conn.execute(
                """insert into _dense
                   select $1, split_part(cell_id, '_', 1)::int * 7200 + split_part(cell_id, '_', 2)::int,
                          (ym || '-01')::date, modis_raw::smallint, viirs_raw::smallint, harmonized::real,
                          harmonized_low::real, harmonized_high::real, anomaly_z::real, {noaa20}
                   from _cal""".format(noaa20="noaa20_raw::smallint" if "noaa20_raw" in header else "null::smallint"),
                release_id,
            )
        except asyncpg.UniqueViolationError:
            raise ContractError("calendar: (cell_id, ym) is not unique") from None
        rep.n_cell_months = int(n.split()[-1])
        log(f"[{region}] {rep.n_cell_months:,} cell-months loaded; checking invariants...")
        # Fresh statistics before the checks: otherwise the planner still thinks these tables are small
        # and picks nested-loop joins over millions of rows (minutes instead of seconds).
        await conn.execute("analyze _dense; analyze release_cell; analyze region_month")

        R = release_id
        n_expected = len(cells) * len(months)
        if rep.n_cell_months != n_expected:
            errors.append(f"calendar has {rep.n_cell_months:,} rows; {len(cells)} cells × {len(months)} months = {n_expected:,}")
        errors += await _check(conn, """
            select cm.cell_key, cm.ym from _dense cm
            left join release_cell rc on rc.release_id = cm.release_id and rc.cell_key = cm.cell_key
            left join region_month rm on rm.release_id = cm.release_id and rm.ym = cm.ym
            where cm.release_id = $1 and (rc.cell_key is null or rm.ym is null)""",
            "calendar row for a cell or month not in cells.geojson / region_monthly", R)
        errors += await _check(conn, """
            select cell_key, ym, harmonized_low, harmonized, harmonized_high from _dense
            where release_id = $1 and (
                (harmonized is null) <> (harmonized_low is null) or (harmonized is null) <> (harmonized_high is null)
                or harmonized_low > harmonized + 1e-4 or harmonized > harmonized_high + 1e-4)""",
            "harmonized_low <= harmonized <= harmonized_high", R)
        errors += await _check(conn, """
            select cm.cell_key, cm.ym, cm.harmonized, rm.data_available from _dense cm
            join region_month rm using (release_id, ym)
            where cm.release_id = $1 and (cm.harmonized is null) = rm.data_available""",
            "harmonized is null iff data_available is false", R)
        errors += await _check(conn, """
            select cm.cell_key, cm.ym, cm.harmonized, cm.viirs_raw from _dense cm
            join region_month rm using (release_id, ym)
            where cm.release_id = $1 and rm.data_available
              and (rm.source = $2 or (rm.source is null and not rm.is_estimate))
              and (cm.viirs_raw is null or abs(cm.harmonized - cm.viirs_raw) > 1e-4)""",
            "observed S-NPP months: harmonized == viirs_raw", R, C.SOURCE_SNPP)
        # v0.5: NOAA-20 months are c_m x noaa20_raw (meta.calibration.continuation.factors).
        cont = ((meta.get("calibration") or {}).get("continuation") or {}).get("factors") or []
        if cont:
            c_by_month = [None] * 12
            for f in cont:
                c_by_month[f["month"] - 1] = f["c"]
            errors += await _check(conn, """
                select cm.cell_key, cm.ym, cm.harmonized, cm.noaa20_raw from _dense cm
                join region_month rm using (release_id, ym)
                where cm.release_id = $1 and rm.source = $2
                  and (cm.noaa20_raw is null
                       or abs(cm.harmonized - ($3::float8[])[extract(month from cm.ym)::int] * cm.noaa20_raw) > 1e-3)""",
                "NOAA-20 months: harmonized == c_m * noaa20_raw", R, C.SOURCE_NOAA20, c_by_month)
        errors += await _check(conn, """
            select cell_key, ym, viirs_raw from _dense
            where release_id = $1 and ym < date '2012-01-01' and viirs_raw is not null""",
            "viirs_raw must be null before 2012-01", R)
        # Region totals are sums over all cells (persistent included). Cell values are rounded in the
        # CSV, so allow a rounding tolerance that grows with the number of cells.
        errors += await _check(conn, """
            select rm.ym, rm.harmonized, s.h, rm.modis_raw, s.m, rm.viirs_raw, s.v, rm.noaa20_raw, s.n from region_month rm
            join (select ym, sum(harmonized::float8) h, sum(modis_raw) m, sum(viirs_raw) v, sum(noaa20_raw) n
                  from _dense where release_id = $1 group by ym) s using (ym)
            where rm.release_id = $1 and (
                abs(coalesce(rm.harmonized, 0) - coalesce(s.h, 0)) > 0.01 + 1e-4 * $2
                or rm.modis_raw is distinct from s.m::int or rm.viirs_raw is distinct from s.v::int
                or rm.noaa20_raw is distinct from s.n::int)""",
            "region_monthly totals == sum over cells", R, len(cells))

        if check_series and series:
            await conn.execute(
                "create temp table _series (cell_key int, ym date, h double precision, m int, v int) on commit drop"
            )
            await conn.copy_records_to_table("_series", records=series)
            await conn.execute("create temp table _series_cell (cell_key int, year int, primary key (year, cell_key)) on commit drop")
            await conn.copy_records_to_table("_series_cell", records=[(k, y) for y, keys in listed.items() for k in keys])
            await conn.execute("create index on _series (cell_key, ym); analyze _series; analyze _series_cell")
            rep.n_series_files = len(listed)
            errors += await _check(conn, """
                select s.cell_key, s.ym, s.h, cm.harmonized, s.m, cm.modis_raw, s.v, cm.viirs_raw from _series s
                left join _dense cm on cm.release_id = $1 and cm.cell_key = s.cell_key and cm.ym = s.ym
                where cm.cell_key is null
                   or (s.h is null) <> (cm.harmonized is null) or abs(s.h - cm.harmonized) > 0.006
                   or s.m is distinct from cm.modis_raw or s.v is distinct from cm.viirs_raw""",
                "series files equal the calendar", R)
            # Cells left out of a year's file must have had no fire-days that year.
            errors += await _check(conn, """
                select cm.cell_key, cm.ym, cm.harmonized, cm.modis_raw, cm.viirs_raw from _dense cm
                join region_month rm using (release_id, ym)
                where cm.release_id = $1
                  and extract(year from cm.ym)::int = any($2::int[])
                  and not exists (select 1 from _series_cell sc where sc.cell_key = cm.cell_key and sc.year = extract(year from cm.ym)::int)
                  and (coalesce(cm.modis_raw, 0) <> 0 or coalesce(cm.viirs_raw, 0) <> 0
                       or (rm.data_available and cm.harmonized <> 0))""",
                "cells omitted from a series file must have no fire-days", R, list(listed))
        if errors:
            raise ContractError(_summary(errors))

        stored = await conn.fetchval("select sparsify_cells('_dense', $1)", release_id)
        log(f"[{region}] stored {stored:,} of {rep.n_cell_months:,} cell-months (the rest are rebuilt as zeros)")
        # The view must give back exactly the calendar that was checked, nulls included.
        cols = "cell_key, ym, modis_raw, viirs_raw, harmonized, harmonized_low, harmonized_high, anomaly_z, noaa20_raw"
        errors = await _check(conn, f"""
            select * from ((select {cols} from cell_month where release_id = $1
                            except all select {cols} from _dense)
                           union all
                           (select {cols} from _dense
                            except all select {cols} from cell_month where release_id = $1)) x""",
            "sparse storage rebuilds the calendar exactly", release_id)
        if errors:
            raise ContractError(_summary(errors))

        cal_meta = meta.get("calibration") or {}
        factors = [("level", f) for f in cal_meta.get("factors", [])]
        factors += [("shape", f) for f in ((cal_meta.get("composite") or {}).get("shape") or {}).get("factors", [])]
        # v0.5 NOAA-20 -> S-NPP factors c_m, stored in the a columns.
        factors += [("continuation", {"month": f["month"], "a": f["c"], "a_low": f.get("c_low"), "a_high": f.get("c_high")})
                    for f in (cal_meta.get("continuation") or {}).get("factors", [])]
        if factors:
            await conn.copy_records_to_table(
                "calibration_factor",
                records=[(R, model, f["month"], f.get("a"), f.get("a_low"), f.get("a_high"), f.get("b"),
                          f.get("b_low"), f.get("b_high"), f.get("w_local")) for model, f in factors],
            )

        if export_fingerprint(folder, source.name) != fingerprint:
            raise ContractError(f"{folder}: export changed during ingest")
        if make_current:
            await conn.execute("update release set is_current = false where region_id = $1 and is_current", region)
            await conn.execute("update release set is_current = true where release_id = $1", R)

    rep.n_cells, rep.n_months, rep.seconds = len(cells), len(months), time.perf_counter() - t0
    log(f"[{region}] release {R} ready{' and current' if make_current else ''} ({rep.seconds:.1f}s)")
    return rep
