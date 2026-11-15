"""firecal-db: set up the database, load exports, manage releases, run the API."""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
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


def _weather_fields(args) -> list[str]:
    from . import weather as W

    fields = args.fields.split(",") if args.fields else list(W.FIELDS)
    bad = [f for f in fields if f not in W.FIELDS]
    if bad:
        raise SystemExit(f"unknown --fields {bad}; choose from {','.join(W.FIELDS)}")
    return fields


def _need_credentials():
    from . import weather as W

    creds = W.credentials()
    if not creds:
        raise SystemExit("METEOMATICS_USER / METEOMATICS_PASSWORD are not set (backend/.env, or the root .env for Docker)")
    return creds


async def cmd_weather_check(args) -> int:
    from . import weather as W

    creds = _need_credentials()
    fields = _weather_fields(args)
    try:
        conn = await connect(settings().database_url)
        try:
            await migrate(conn)
            await W.take_quota(conn, W.daily_cap())
        finally:
            await conn.close()
    except W.QuotaReached as e:
        print(e)
        return 1
    try:
        res = await asyncio.to_thread(W.check, creds, args.lat, args.lon, fields)
    except W.MeteomaticsError as e:
        print(f"Meteomatics refused the request: {e}{W.hint(e.status)}")
        return 1
    print(f"OK: {args.lat},{args.lon} on {res['day']} ({res['seconds']} s)")
    for f in fields:
        print(f"  {W.FIELDS[f][0]:<36} {res[f]}")
    return 0


async def cmd_weather_fetch(args) -> int:
    from . import weather as W

    creds = None if args.dry_run else _need_credentials()
    fields = _weather_fields(args)
    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        return await W.fetch_all(
            conn, args.regions, creds, fields, wait_lock=args.wait_lock, chunk_months=args.chunk_months, dry_run=args.dry_run
        )
    finally:
        await conn.close()


async def cmd_weather_export(args) -> int:
    from . import weather as W

    conn = await connect(settings().database_url)
    try:
        return await W.export_dir(conn, Path(args.folder))
    finally:
        await conn.close()


async def cmd_weather_import(args) -> int:
    from . import weather as W

    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        return await W.import_dir(conn, Path(args.folder))
    finally:
        await conn.close()


async def cmd_send_alerts(args) -> int:
    from .alerts import run_alerts

    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        results = await run_alerts(conn, dry_run=args.dry_run)
    finally:
        await conn.close()
    for r in results:
        z = "-" if r.z is None else f"{r.z:+.2f}"
        print(f"[area {r.area_id}] {r.area} ({r.email}) {r.ym or '-'} z={z}: {r.reason}")
    print(f"{sum(r.sent for r in results)} alert(s) queued, {len(results)} area(s) checked")
    return 0


async def cmd_send_digest(args) -> int:
    from .alerts import run_digest

    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        n = await run_digest(conn, dry_run=args.dry_run)
    finally:
        await conn.close()
    print(f"digest {'would go' if args.dry_run else 'queued'} to {n} subscriber(s)")
    return 0


async def cmd_send_outbox(args) -> int:
    from . import mailer

    if mailer.smtp_settings() is None:
        print("SMTP_HOST is not set: emails stay in the outbox (see /dev/outbox locally)")
        return 1
    conn = await connect(settings().database_url)
    try:
        sent, failed = await mailer.deliver(conn, limit=args.limit)
    finally:
        await conn.close()
    print(f"sent {sent}, failed {failed}")
    return 1 if failed else 0


# ---------------------------------------------------------------- live pipeline


def _firms_key() -> str:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        raise SystemExit("FIRMS_MAP_KEY is not set (backend/.env). Get a free key at https://firms.modaps.eosdis.nasa.gov/api/map_key/")
    return key


def _publisher(conn, direct: bool):
    """Where events go: the Event Hubs stream, or (--direct) straight into the consumer on this machine."""
    from .live import consumer as LC
    from .live import eventhub as EH
    from .live import firms as F

    conn_str = os.environ.get("EVENTHUB_CONNECTION", "").strip()
    if direct or not conn_str:
        if not direct:
            print("EVENTHUB_CONNECTION is not set: handling events here instead of sending them to the stream")

        async def local(events):
            print("  ", await LC.process(conn, events))

        return local
    hub = EH.parse_connection(conn_str, os.environ.get("EVENTHUB_NAME") or None)

    def stream(events):
        n = EH.send(hub, [F.dumps(e) for e in events])
        print(f"   sent {len(events)} events to the stream {hub.name} in {n} request(s)")

    return stream


async def cmd_live_poll(args) -> int:
    from .live import poller as P

    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        await P.poll(conn, _firms_key(), _publisher(conn, args.direct), days=args.days)
        return 0
    finally:
        await conn.close()


async def cmd_live_backfill(args) -> int:
    """Load every day since the releases' last day of data. Stored directly: far too many events to replay one by one."""
    from datetime import datetime, timezone

    from .live import consumer as LC
    from .live import firms as F
    from .live import poller as P
    from .live import store as S

    key = _firms_key()
    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        rels = await S.current_releases(conn)
        if not rels:
            print("no releases loaded")
            return 1
        today = datetime.now(timezone.utc).date()
        first = date.fromisoformat(args.since) if args.since else min(S.live_first_month(r) for r in rels)
        boxes = P.poll_boxes(rels)
        total = 0
        for source, a, b in P.backfill_plan(first, today):
            for box in boxes:
                d = a
                while d <= b:
                    n = min(F.MAX_DAYS, (b - d).days + 1)
                    events = F.fetch(key, source, box, n, d)
                    r = await LC.process(conn, events, resync=False)
                    total += r["new"]
                    print(f"{source} {d}..{d + timedelta(days=n - 1)} box {box}: {len(events)} detections, {r['new']} new")
                    d += timedelta(days=n)
        await S.advance_coverage(conn, today, polled_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        for m in await S.sync(conn, force=True):
            print(f"  {m['region']} {m['ym']}: {m['fire_days']} fire-days from {m['detections']} detections")
        print(f"backfill done: {total} new detections")
        return 0
    finally:
        await conn.close()


async def cmd_live_recompute(args) -> int:
    from .live import store as S

    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        for m in await S.sync(conn, force=True, regions=args.regions or None):
            print(f"{m['region']} {m['ym']}{' (demo)' if m['demo'] else ''}: {m['fire_days']} fire-days -> {m['harmonized']:.2f} harmonized")
        return 0
    finally:
        await conn.close()


async def cmd_live_status(args) -> int:
    from .live import store as S

    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        for k in ("coverage", "poller", "consumer"):
            print(f"{k}: {await S.get_state(conn, k)}")
        for rel in await S.current_releases(conn):
            st = await S.status(conn, rel, False)
            print(f"[{rel['region_id']}] live {st['first_month']}..{st['last_month']}, last detection {st['last_detection_at']}, "
                  f"{st['detections_24h']} received in 24 h, harmonization {st['harmonization']['version']}")
            for m in st["months"]:
                print(f"    {m['ym']}: {m['fire_days']} fire-days -> {m['harmonized']:.2f} (through {m['through']}{', partial' if m['partial_month'] else ''}) {m['sensors']}")
        return 0
    finally:
        await conn.close()


async def cmd_live_replay(args) -> int:
    from .live import replay as R
    from .live import store as S

    key = _firms_key()
    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        rel = next(iter(await S.current_releases(conn, [args.region])), None)
        if not rel:
            print(f"no current release for {args.region}")
            return 1
        first, last, what = R.PRESETS.get(args.region, (None, None, "custom period"))
        if args.frm and args.to:
            first, last, what = date.fromisoformat(args.frm), date.fromisoformat(args.to), "custom period"
        if not first:
            print("give --from and --to (no preset for this region)")
            return 1
        print(f"replaying {what} ({first}..{last}) into {args.region}, as if it ended today")
        days = R.load(key, list(rel["bbox"]), first, last)
        publish = _publisher(conn, args.direct)
        for i, (day, events) in enumerate(days):
            print(f"  day {i + 1}/{len(days)} ({day}): {len(events)} simulated detections")
            r = publish(events)
            if hasattr(r, "__await__"):
                await r
            if i < len(days) - 1:
                await asyncio.sleep(args.step_seconds)
        print("done. Remove the demo data with: firecal-db live-clear-demo")
        return 0
    finally:
        await conn.close()


async def cmd_live_clear_demo(args) -> int:
    from .live import store as S

    conn = await connect(settings().database_url)
    try:
        await migrate(conn)
        print(f"removed {await S.clear_demo(conn)} simulated detections and the demo months")
        return 0
    finally:
        await conn.close()


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
    fields_help = "comma-separated subset of t_mean_c,t_max_c,precip_mm,wind_ms,rh_pct (default: all)"
    wc = sub.add_parser("weather-check", help="one small Meteomatics request, to test the credentials and parameters")
    wc.add_argument("--lat", type=float, default=33.89)
    wc.add_argument("--lon", type=float, default=35.50)
    wc.add_argument("--fields", help=fields_help)
    wf = sub.add_parser("weather-fetch", help="fetch the months of weather not stored yet (stops at the daily cap)")
    wf.add_argument("regions", nargs="*", help="default: every region with a current release")
    wf.add_argument("--fields", help=fields_help)
    wf.add_argument("--chunk-months", type=int, default=12, help="months per request (split automatically if too large)")
    wf.add_argument("--dry-run", action="store_true", help="show what would be fetched, without sending requests")
    wf.add_argument("--wait-lock", type=float, default=0, metavar="SECONDS",
                    help="if another fetch is running, keep retrying this long instead of skipping (default: skip)")
    we = sub.add_parser("weather-export", help="write stored weather to <folder>/<region>.json")
    we.add_argument("folder")
    wi = sub.add_parser("weather-import", help="load <region>.json files written by weather-export")
    wi.add_argument("folder")
    lp = sub.add_parser("live-poll", help="fetch recent FIRMS detections and publish the new ones (stream, or --direct)")
    lp.add_argument("--days", type=int, default=2, help="days to look back (1-5)")
    lp.add_argument("--direct", action="store_true", help="handle the events here instead of sending them to the stream")
    lb = sub.add_parser("live-backfill", help="load every day since the releases' last day of data, straight into the database")
    lb.add_argument("--since", help="YYYY-MM-DD (default: the day after the releases' last VIIRS day)")
    lr = sub.add_parser("live-recompute", help="rebuild the live months (after the harmonization changed)")
    lr.add_argument("regions", nargs="*")
    sub.add_parser("live-status", help="what the live pipeline has stored")
    ly = sub.add_parser("live-replay", help="demo: replay a past outbreak as simulated live detections")
    ly.add_argument("region")
    ly.add_argument("--from", dest="frm", help="YYYY-MM-DD (default: the region's preset outbreak)")
    ly.add_argument("--to", help="YYYY-MM-DD")
    ly.add_argument("--step-seconds", type=float, default=8, help="pause between replayed days")
    ly.add_argument("--direct", action="store_true", help="handle the events here instead of sending them to the stream")
    sub.add_parser("live-clear-demo", help="remove the simulated detections and demo months")
    sa = sub.add_parser("send-alerts", help="email users whose saved areas had an unusually high month")
    sa.add_argument("--dry-run", action="store_true", help="show what would be sent, without queueing emails")
    sd = sub.add_parser("send-digest", help="queue the monthly digest for confirmed email-list subscribers")
    sd.add_argument("--dry-run", action="store_true", help="print the digest and the number of recipients only")
    so = sub.add_parser("send-outbox", help="send queued emails over SMTP (needs SMTP_HOST)")
    so.add_argument("--limit", type=int, default=200)
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
          "set-current": cmd_set_current, "delete-release": cmd_delete_release,
          "weather-check": cmd_weather_check, "weather-fetch": cmd_weather_fetch,
          "weather-export": cmd_weather_export, "weather-import": cmd_weather_import,
          "live-poll": cmd_live_poll, "live-backfill": cmd_live_backfill, "live-recompute": cmd_live_recompute,
          "live-status": cmd_live_status, "live-replay": cmd_live_replay, "live-clear-demo": cmd_live_clear_demo,
          "send-alerts": cmd_send_alerts, "send-digest": cmd_send_digest, "send-outbox": cmd_send_outbox}[args.cmd]
    sys.exit(asyncio.run(fn(args)))


if __name__ == "__main__":
    main()
