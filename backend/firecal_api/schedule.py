"""Monthly schedule for the weather fetch (`python -m firecal_api.cli weather-schedule`).

- A job that never finished runs right away; after that it runs on day SCHEDULE_DAY (default 1) of every month
  at SCHEDULE_HOUR_UTC (default 3).
- A run missed while the machine was off runs at the next start.
- A run that could not finish (daily cap reached, network or Meteomatics error) is retried after
  SCHEDULE_RETRY_HOURS (default 6). An interrupted run (container stopped mid-run) is retried right away.
- After every run the stored weather is written to WEATHER_DIR/<region>.json, so it survives the database.

State lives in the job_run table (sql/004_job_run.sql), next to the data it describes: a fresh database
means a fresh first run.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

import asyncpg

from .config import settings
from .db import connect, migrate

UTC = timezone.utc
CHECK_EVERY = timedelta(hours=6)  # sleep in steps, so a clock change or a suspended laptop can't overshoot much


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    v = int(os.environ.get(name, default))
    if not lo <= v <= hi:
        raise SystemExit(f"{name} must be between {lo} and {hi}, got {v}")
    return v


def slot_after(t: datetime, day: int, hour: int) -> datetime:
    """First scheduled time (day `day` of a month, `hour`:00 UTC) strictly after t."""
    s = datetime(t.year, t.month, day, hour, tzinfo=UTC)
    if s <= t:
        y, m = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
        s = datetime(y, m, day, hour, tzinfo=UTC)
    return s


def due_at(state: asyncpg.Record | dict | None, day: int, hour: int, retry: timedelta, now: datetime) -> datetime:
    if not state or state["last_attempt"] is None:
        return now                                            # never ran
    ok, attempt, result = state["last_ok"], state["last_attempt"], state["last_result"]
    if result == "running":
        return now                                            # interrupted: carry on
    if ok is None or attempt > ok:
        return attempt + retry                                # last run did not finish
    return slot_after(ok, day, hour)


async def get_state(conn: asyncpg.Connection, job: str):
    return await conn.fetchrow("select * from job_run where job = $1", job)


async def mark(conn: asyncpg.Connection, job: str, result: str, ok: bool = False, started: bool = False) -> None:
    now = datetime.now(UTC)
    await conn.execute(
        """insert into job_run (job, last_ok, last_attempt, last_result) values ($1, $2, $3, $4)
           on conflict (job) do update set
             last_ok = coalesce(excluded.last_ok, job_run.last_ok),
             last_attempt = coalesce(excluded.last_attempt, job_run.last_attempt),
             last_result = excluded.last_result""",
        job, now if ok else None, now if started else None, result,
    )


async def run_forever(job: str, run: Callable[[asyncpg.Connection], Awaitable[tuple[bool, str]]],
                      log: Callable[[str], None] = print) -> None:
    day = _env_int("SCHEDULE_DAY", 1, 1, 28)
    hour = _env_int("SCHEDULE_HOUR_UTC", 3, 0, 23)
    retry = timedelta(hours=_env_int("SCHEDULE_RETRY_HOURS", 6, 1, 24 * 27))
    announced = None
    while True:
        conn = await connect(settings().database_url)
        try:
            await migrate(conn)
            now = datetime.now(UTC)
            due = due_at(await get_state(conn, job), day, hour, retry, now)
            if due > now:
                if due != announced:
                    log(f"[{job}] next run {due:%Y-%m-%d %H:%M} UTC")
                    announced = due
            else:
                log(f"[{job}] starting")
                await mark(conn, job, "running", started=True)
                try:
                    ok, msg = await run(conn)
                except Exception as e:  # noqa: BLE001 - keep the schedule alive, retry later
                    ok, msg = False, f"{type(e).__name__}: {e}"
                await mark(conn, job, "ok" if ok else msg, ok=ok)
                log(f"[{job}] {'finished' if ok else 'did not finish: ' + msg}")
                continue
        finally:
            await conn.close()
        await asyncio.sleep(min(CHECK_EVERY, due - datetime.now(UTC)).total_seconds() + 1)


async def weather_job(conn: asyncpg.Connection) -> tuple[bool, str]:
    from . import weather as W

    creds = W.credentials()
    if creds is None:
        return False, "METEOMATICS_USER / METEOMATICS_PASSWORD not set"
    fields = list(W.FIELDS)
    rc = await W.fetch_all(conn, None, creds, fields, wait_lock=900)
    remaining = 0
    for rel in await conn.fetch("select * from release where is_current order by region_id"):
        remaining += await W.fetch_region(conn, rel, None, fields, dry_run=True, log=lambda *_: None)
    folder = os.environ.get("WEATHER_DIR")
    if folder:
        await W.export_dir(conn, Path(folder))
    if rc != 0:
        return False, "Meteomatics refused the requests (see the log above)"
    if remaining:
        return False, f"about {remaining} requests still to send (daily cap reached)"
    return True, "ok"
