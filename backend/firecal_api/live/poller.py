"""One polling pass: ask FIRMS for recent detections, drop the ones stored already, publish the rest."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import asyncpg

from . import firms as F
from . import store as S


def poll_boxes(releases) -> list[list[float]]:
    """Bounding boxes to poll: every region's box, without those lying inside another."""
    boxes = sorted({tuple(r["bbox"]) for r in releases}, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    out: list[tuple] = []
    for b in boxes:
        if not any(o[0] <= b[0] and o[1] <= b[1] and o[2] >= b[2] and o[3] >= b[3] for o in out):
            out.append(b)
    return [list(b) for b in out]


async def poll(conn: asyncpg.Connection, key: str, publish: Callable[[list[dict]], object], *,
               sources=F.LIVE_SOURCES, days: int = 2, max_catch_up_days: int = 400, get=F.http_get,
               log: Callable[[str], None] = print) -> dict:
    """Fetch every region box since the last poll and publish the detections not stored yet.

    The window starts `days` days back, or at the day before the last covered day when that is earlier,
    so the schedule can be anything (every 15 minutes, hourly, monthly): a slow schedule simply catches
    up, in FIRMS requests of at most 5 days. publish(events) sends them on (to the stream, or straight to
    the consumer). A coverage event follows, so months get their "data through" day even when nothing burned.
    """
    boxes = poll_boxes(await S.current_releases(conn))
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=max(days, 1) - 1)
    covered = await S.get_coverage(conn)
    if covered:
        first = max(min(first, covered - timedelta(days=1)), today - timedelta(days=max_catch_up_days))
    found: dict[str, dict] = {}
    for source in sources:
        for box in boxes:
            for e in F.fetch_range(key, source, box, first, today, get=get):
                found[e["id"]] = e
    known = await S.known_ids(conn, list(found)) if found else set()
    new = [e for i, e in found.items() if i not in known]
    # FIRMS returns whole UTC days; yesterday is complete, today is still filling.
    events = [*new, F.coverage_event(today, sources)]
    r = publish(events)
    if hasattr(r, "__await__"):
        await r
    summary = {"seen": len(found), "new": len(new), "boxes": len(boxes), "sources": list(sources),
               "from": first.isoformat(), "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    await S.set_state(conn, "poller", summary)
    log(f"FIRMS: {len(found)} detections since {first}, {len(new)} new")
    return summary


def backfill_plan(first, last, snpp_last=None) -> list[tuple[str, object, object]]:
    """(source, first day, last day) to fetch for a past period: S-NPP while it flew, NOAA-20 for all of it."""
    from .harmonize import SNPP_LAST_DAY

    snpp_last = snpp_last or SNPP_LAST_DAY
    plan = []
    if first <= snpp_last:
        plan.append(("VIIRS_SNPP_NRT", first, min(last, snpp_last)))
    plan.append(("VIIRS_NOAA20_NRT", first, last))
    return plan


def recent_window(days: int):
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=days - 1), today
