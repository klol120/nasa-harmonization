"""Refresh Phoenical's outlook from the production calendar and completed live observations."""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np

from . import contract as C, outlook as O
from .config import settings
from .db import connect
from .live import harmonize as H, store as L

CHECK_INTERVAL = timedelta(days=15)


@dataclass(frozen=True)
class InputMonths:
    release_id: int
    archive: tuple[date, ...]
    live: tuple[tuple[date, datetime], ...]

    @property
    def issue(self) -> str:
        return C.ym_str(max(self.archive + tuple(ym for ym, _ in self.live)))


async def input_months(conn, rel, before: date) -> InputMonths:
    rid = rel["release_id"]
    archive = tuple(await conn.fetchval(
        """select array(select ym from region_month where release_id = $1 and ym < $2
           and data_available and not partial_month and not is_estimate order by ym)""",
        rid, before,
    ))
    live = await conn.fetch(
        """select ym, updated_at from live_region_month
           where region_id = $1 and release_id = $2 and ym < $3 and not demo and not partial_month
             and not provisional and harmonization = $4 and through = (ym + interval '1 month - 1 day')::date
           order by ym""",
        rel["region_id"], rid, before, H.VERSION,
    )
    return InputMonths(rid, archive, tuple((row["ym"], row["updated_at"]) for row in live if row["ym"] not in archive))


async def load_region(conn, rel, source: InputMonths) -> O.Region:
    name, rid = rel["region_id"], source.release_id
    grid = await conn.fetch(
        """select c.cell_key, c.cell_id, c.lat_center, c.lon_center from release_cell rc
           join cell c using (cell_key) where rc.release_id = $1 order by c.cell_key""", rid,
    )
    live_months = [ym for ym, _ in source.live]
    observed = set(source.archive) | set(live_months)
    dates = C.month_range(rel["first_month"], max(observed))
    col = {ym: j for j, ym in enumerate(dates)}
    row = {cell["cell_key"]: i for i, cell in enumerate(grid)}
    ok = np.array([ym in observed for ym in dates])
    values = np.full((len(grid), len(dates)), np.nan, dtype=np.float32)
    values[:, ok] = 0  # Stored live cell rows are sparse; covered cells without detections are zero.

    async for key, ym, value in conn.cursor(
        """select cell_key, ym, harmonized from cell_month_data
           where release_id = $1 and ym = any($2::date[]) and harmonized > 0
           union all
           select lc.cell_key, lc.ym, lc.harmonized from live_cell_month lc
           join release_cell rc on rc.release_id = $1 and rc.cell_key = lc.cell_key
           where lc.region_id = $3 and lc.ym = any($4::date[]) and not lc.demo and lc.harmonized > 0""",
        rid, source.archive, name, live_months,
    ):
        values[row[key], col[ym]] = value
    return O.Region(
        name=name, months=[C.ym_str(ym) for ym in dates], cells=[cell["cell_id"] for cell in grid],
        V=values, ok=ok, lat=np.array([cell["lat_center"] for cell in grid], dtype=np.float32),
        lon=np.array([cell["lon_center"] for cell in grid], dtype=np.float32),
        mean=O._nanmean(values, axis=0).astype(np.float32),
    )


async def due(conn, source: InputMonths) -> bool:
    return not await conn.fetchval(
        """select exists (select 1 from model_run
           where release_id = $1 and model_name = $2 and model_version = $3 and metrics->>'issued_after' >= $4)""",
        source.release_id, O.MODEL_NAME, O.MODEL_VERSION, source.issue,
    )


async def refresh(database_url: str, names: list[str] | None = None, *, on_deploy=False) -> None:
    conn = await connect(database_url)
    try:
        # Share the publisher's lock with the CLI so replicas cannot duplicate training or publication.
        if not await conn.fetchval("select pg_try_advisory_lock(hashtext($1))", O.MODEL_NAME):
            print("Outlook refresh already running.")
            return
        today = datetime.now(timezone.utc).date()
        before = today.replace(day=1)
        scope = ",".join(sorted(set(names))) if names else "all-countries"
        check_key = f"outlook-check:{O.MODEL_VERSION}:{scope}"
        last_check = await L.get_state(conn, check_key)
        if not on_deploy and last_check and today < date.fromisoformat(last_check["date"]) + CHECK_INTERVAL:
            print("Next outlook check is not due yet.")
            return
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            releases = {r["region_id"]: r for r in await L.current_releases(conn, names) if len(r["countries"]) == 1}
            if not releases:
                raise RuntimeError("Outlook refresh has no single-country calendar releases.")
            sources = {name: await input_months(conn, rel, before) for name, rel in releases.items()}
            pending = [name for name, source in sources.items() if await due(conn, source)]
            regions = [await load_region(conn, releases[name], source) for name, source in sources.items()] if pending else []

        if not pending:
            await L.set_state(conn, check_key, {"date": today.isoformat()})
            print("Outlooks already cover the latest complete observations.")
            return

        result = await asyncio.to_thread(O.run_regions, regions)
        O.print_summary(result["report"])
        async with conn.transaction(isolation="repeatable_read"):
            current = await conn.fetch(
                """select * from release where is_current and region_id = any($1::text[]) order by region_id for share""",
                list(sources),
            )
            snapshot = {r["region_id"]: await input_months(conn, r, before) for r in current}
            if snapshot != sources:
                raise RuntimeError("Outlook input changed during training. The next execution will retry.")
            provenance = {
                "training_releases": {name: source.release_id for name, source in sources.items()},
                "live_input_versions": {
                    name: {C.ym_str(ym): stamp.isoformat() for ym, stamp in source.live}
                    for name, source in sources.items()
                },
            }
            for name in pending:
                await O.write_run(conn, name, sources[name].release_id, result["live"][name], result["report"], provenance)
            await L.set_state(conn, check_key, {"date": today.isoformat()})
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+")
    parser.add_argument("--on-deploy", action="store_true", help="check now, regardless of the 15-day interval")
    args = parser.parse_args()
    asyncio.run(refresh(settings().database_url, args.regions, on_deploy=args.on_deploy))


if __name__ == "__main__":
    main()
