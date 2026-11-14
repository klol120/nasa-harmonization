"""firecal-db: set up the database, load exports, manage releases, run the API."""

import argparse
import asyncio
import sys
from pathlib import Path

from .config import settings
from .contract import ContractError
from .db import connect, ensure_database, migrate
from .ingest import ingest_region


async def cmd_init(args) -> int:
    url = settings().database_url
    if await ensure_database(url):
        print("created database")
    conn = await connect(url)
    try:
        applied = await migrate(conn)
        print("applied: " + ", ".join(applied) if applied else "schema up to date")
    finally:
        await conn.close()
    return 0


async def cmd_ingest(args) -> int:
    s = settings()
    if args.paths:
        folders = [Path(p) for p in args.paths]
    else:
        folders = sorted(p for p in s.export_dir.iterdir() if (p / "meta.json").is_file())
        if not folders:
            print(f"no region folders (with meta.json) under {s.export_dir}")
            return 1
    conn = await connect(s.database_url)
    failed = 0
    try:
        await migrate(conn)
        for folder in folders:
            try:
                rep = await ingest_region(
                    conn, folder, check_series=not args.no_series, make_current=not args.no_current, force=args.force
                )
                for w in rep.warnings:
                    print(f"[{rep.region}] warning: {w}")
            except ContractError as e:
                failed += 1
                print(f"[{folder.name}] REJECTED, nothing was loaded. {e}", file=sys.stderr)
    finally:
        await conn.close()
    return 1 if failed else 0


async def cmd_releases(args) -> int:
    conn = await connect(settings().database_url)
    try:
        rows = await conn.fetch(
            """select r.release_id, r.region_id, r.is_current, r.contract_version, r.generated_at, r.loaded_at, r.n_cells,
                      (select count(*) from model_run m where m.release_id = r.release_id) runs
               from release r order by r.region_id, r.release_id desc"""
        )
    finally:
        await conn.close()
    print(f"{'id':>5}  {'region':<10} {'cur':<4} {'ver':<5} {'generated':<20} {'cells':>7} {'runs':>5}")
    for r in rows:
        gen = r["generated_at"].strftime("%Y-%m-%d %H:%M") if r["generated_at"] else "?"
        print(f"{r['release_id']:>5}  {r['region_id']:<10} {'*' if r['is_current'] else '':<4} {r['contract_version']:<5} "
              f"{gen:<20} {r['n_cells']:>7} {r['runs']:>5}")
    return 0


async def cmd_set_current(args) -> int:
    conn = await connect(settings().database_url)
    try:
        async with conn.transaction():
            region = await conn.fetchval("select region_id from release where release_id = $1", args.release_id)
            if not region:
                print(f"no release {args.release_id}")
                return 1
            await conn.execute("update release set is_current = false where region_id = $1 and is_current", region)
            await conn.execute("update release set is_current = true where release_id = $1", args.release_id)
        print(f"release {args.release_id} is now current for {region}")
    finally:
        await conn.close()
    return 0


async def cmd_delete_release(args) -> int:
    conn = await connect(settings().database_url)
    try:
        r = await conn.fetchrow("select region_id, is_current from release where release_id = $1", args.release_id)
        if not r:
            print(f"no release {args.release_id}")
            return 1
        if r["is_current"] and not args.yes:
            print(f"release {args.release_id} is the current release of {r['region_id']}; pass --yes to delete it anyway")
            return 1
        await conn.execute("delete from release where release_id = $1", args.release_id)
        print(f"deleted release {args.release_id} ({r['region_id']}) and its model runs")
    finally:
        await conn.close()
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="firecal-db", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the database (if missing) and apply the schema")
    i = sub.add_parser("ingest", help="load export folders (default: every region under EXPORT_DIR)")
    i.add_argument("paths", nargs="*", help="region folders, e.g. ../pipeline/data/export/lebanon")
    i.add_argument("--no-series", action="store_true", help="skip checking cells_series files against the calendar")
    i.add_argument("--no-current", action="store_true", help="load without making it the current release")
    i.add_argument("--force", action="store_true", help="load even if this exact export is already loaded")
    sub.add_parser("releases", help="list loaded releases")
    sc = sub.add_parser("set-current", help="make a release its region's current one (e.g. to roll back)")
    sc.add_argument("release_id", type=int)
    d = sub.add_parser("delete-release", help="delete a release, its data and its model runs")
    d.add_argument("release_id", type=int)
    d.add_argument("--yes", action="store_true")
    sv = sub.add_parser("serve", help="run the API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    args = p.parse_args()

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("firecal_api.api:app", host=args.host, port=args.port, reload=args.reload)
        return
    fn = {"init": cmd_init, "ingest": cmd_ingest, "releases": cmd_releases,
          "set-current": cmd_set_current, "delete-release": cmd_delete_release}[args.cmd]
    sys.exit(asyncio.run(fn(args)))


if __name__ == "__main__":
    main()
