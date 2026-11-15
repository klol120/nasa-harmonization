"""The stream consumer: what happens to a batch of events (the "harmonization function")."""

import json
from datetime import date, datetime, timezone

import asyncpg

from . import firms as F
from . import store as S


def decode(bodies) -> tuple[list[dict], int]:
    """Event bodies (str/bytes/dict) -> events; returns (events, number that could not be read)."""
    out, bad = [], 0
    for b in bodies:
        try:
            e = b if isinstance(b, dict) else json.loads(b)
            if not isinstance(e, dict) or "type" not in e:
                raise ValueError
            out.append(e)
        except (ValueError, TypeError):
            bad += 1
    return out, bad


async def process(conn: asyncpg.Connection, events: list[dict], *, resync: bool = True) -> dict:
    """Store the detections of a batch and rebuild the months they touch. Safe to run twice on the same batch."""
    rows, bad, cover = [], 0, None
    for e in events:
        if e.get("type") == "detection":
            try:
                rows.append(F.event_row(e))
            except (KeyError, ValueError, TypeError):
                bad += 1
        elif e.get("type") == "coverage":
            try:
                d = date.fromisoformat(e["through"])
                cover = (max(cover[0], d), e) if cover else (d, e)
            except (KeyError, ValueError, TypeError):
                bad += 1
    await conn.execute("select pg_advisory_lock($1)", S.LOCK_KEY)
    try:
        inserted = await S.insert_detections(conn, rows)
        if cover:
            await S.advance_coverage(conn, cover[0], polled_at=cover[1].get("polled_at"), sources=cover[1].get("sources"))
        dirty = await S.affected(conn, inserted)
        rebuilt = await S.sync(conn, dirty) if resync else []
        summary = {
            "events": len(events), "detections": len(rows), "new": len(inserted), "unreadable": bad,
            "months_rebuilt": len(rebuilt), "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        await S.set_state(conn, "consumer", summary)
        return summary
    finally:
        await conn.execute("select pg_advisory_unlock($1)", S.LOCK_KEY)
