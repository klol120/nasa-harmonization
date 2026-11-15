"""Demo mode: replay a past outbreak through the pipeline as if it were happening now.

The detections are real (FIRMS archive) but moved in time so the last day of the outbreak is today, and
marked `simulated`. They only show when the client asks for the demo view and never mix into the real
months. `firecal-db live-clear-demo` removes them.
"""

from datetime import date, datetime, timedelta, timezone

from . import firms as F

# Well-documented outbreaks, by region: (first day, last day, what it was).
PRESETS: dict[str, tuple[date, date, str]] = {
    "greece": (date(2021, 8, 3), date(2021, 8, 12), "Evia and Attica fires, August 2021"),
    "eastmed": (date(2021, 7, 28), date(2021, 8, 6), "Manavgat and the Turkish south coast, July-August 2021"),
    "lebanon": (date(2019, 10, 13), date(2019, 10, 16), "Chouf and Mount Lebanon fires, October 2019"),
}


def shift_events(events: list[dict], last_source_day: date, today: date) -> list[dict]:
    """Move archive detections so `last_source_day` lands on `today`; days that would fall before the
    1st of this month are dropped (the demo stays inside the month in progress)."""
    delta = today - last_source_day
    out = []
    for e in events:
        acq = datetime.strptime(e["acq"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) + delta
        if acq.date() < today.replace(day=1) or acq.date() > today:
            continue
        out.append(F.event("SIM", f"replay:{e['source']}", e["lat"], e["lon"], acq, confidence=e.get("confidence"),
                           frp=e.get("frp"), daynight=e.get("daynight"), simulated=True))
    return out


def by_day(events: list[dict]) -> list[tuple[date, list[dict]]]:
    days: dict[date, list[dict]] = {}
    for e in events:
        days.setdefault(date.fromisoformat(e["acq"][:10]), []).append(e)
    return sorted(days.items())


def load(key: str, bbox, first: date, last: date, source: str = "VIIRS_SNPP_SP", get=F.http_get,
         today: date | None = None) -> list[tuple[date, list[dict]]]:
    """Archive detections of [first, last] in a box, moved to end today, grouped by (shifted) day."""
    today = today or datetime.now(timezone.utc).date()
    # Only as many days as fit in the month so far.
    first = max(first, last - timedelta(days=today.day - 1))
    return by_day(shift_events(F.fetch_range(key, source, bbox, first, last, get=get), last, today))
