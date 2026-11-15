"""NASA FIRMS area API client, and the detection event that travels through the stream.

API: https://firms.modaps.eosdis.nasa.gov/api/area/ (free MAP_KEY, 5,000 transactions per 10 minutes,
at most 5 days per request). Near-real-time (NRT) data appears within about 3 hours of an overpass.
"""

import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from ..contract import GRID_COLS, cell_rc

API_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
MAX_DAYS = 5

# FIRMS source id -> our sensor name.
SENSOR_OF = {
    "VIIRS_SNPP_NRT": "SNPP", "VIIRS_SNPP_SP": "SNPP",
    "VIIRS_NOAA20_NRT": "NOAA20", "VIIRS_NOAA20_SP": "NOAA20",
    "VIIRS_NOAA21_NRT": "NOAA21", "VIIRS_NOAA21_SP": "NOAA21",
}
# NOAA-21 is not used by the pipeline (config sensors.satellites), so it is not polled.
LIVE_SOURCES = ("VIIRS_NOAA20_NRT",)


class FirmsError(RuntimeError):
    pass


def area_url(key: str, source: str, bbox, days: int, start: date | None = None) -> str:
    """bbox: [west, south, east, north]. Without `start`, the most recent `days` days."""
    if source not in SENSOR_OF:
        raise ValueError(f"unknown FIRMS source {source!r}")
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be 1..{MAX_DAYS}")
    w, s, e, n = bbox
    url = f"{API_URL}/{key}/{source}/{w:g},{s:g},{e:g},{n:g}/{days}"
    return f"{url}/{start:%Y-%m-%d}" if start else url


def http_get(url: str, timeout: float = 90) -> str:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "firecal-live"}), timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise FirmsError(f"FIRMS answered {e.code}: {e.read()[:200]!r}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise FirmsError(f"FIRMS not reachable: {e}") from None


def detection_id(sensor: str, acq_at: datetime, lat: float, lon: float, simulated: bool = False) -> str:
    raw = f"{sensor}|{acq_at:%Y%m%d%H%M}|{lat:.5f}|{lon:.5f}"
    return ("sim-" if simulated else "") + hashlib.sha1(raw.encode()).hexdigest()[:24]


def parse_csv(text: str, source: str) -> list[dict]:
    """FIRMS CSV -> detection events. Rows that cannot be read are skipped; an error page raises."""
    head = text.lstrip()[:200].lower()
    if not head.startswith("latitude,"):
        if not head or head.startswith("no data"):
            return []
        raise FirmsError(f"unexpected FIRMS response: {text.strip()[:160]!r}")
    sensor = SENSOR_OF[source]
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            t = f"{int(row['acq_time']):04d}"
            acq = datetime.strptime(f"{row['acq_date']} {t}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        out.append(event(sensor, source, lat, lon, acq, confidence=(row.get("confidence") or None),
                         frp=_num(row.get("frp")), daynight=(row.get("daynight") or None)))
    return out


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def event(sensor: str, source: str, lat: float, lon: float, acq_at: datetime, *, confidence=None, frp=None,
          daynight=None, simulated: bool = False) -> dict:
    """One detection as it travels through the stream (JSON-serialisable)."""
    return {
        "type": "detection", "v": 1,
        "id": detection_id(sensor, acq_at, lat, lon, simulated),
        "sensor": sensor, "source": source, "lat": lat, "lon": lon,
        "acq": acq_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "confidence": confidence, "frp": frp, "daynight": daynight, "simulated": simulated,
    }


def coverage_event(through: date, sources) -> dict:
    """Tells the consumer that every listed source was polled up to this UTC day (even if nothing burned)."""
    return {"type": "coverage", "v": 1, "through": through.isoformat(), "sources": list(sources),
            "polled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def event_row(e: dict) -> tuple:
    """Detection event -> live_detection row. Raises ValueError/KeyError on a malformed event."""
    lat, lon = float(e["lat"]), float(e["lon"])
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("position out of range")
    acq = datetime.strptime(e["acq"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    row, col = cell_rc(lat, lon)
    return (str(e["id"]), str(e["sensor"]), str(e["source"]), lat, lon, acq, acq.date(), row * GRID_COLS + col,
            e.get("confidence"), e.get("frp"), e.get("daynight"), bool(e.get("simulated", False)))


def fetch(key: str, source: str, bbox, days: int, start: date | None = None, get=http_get) -> list[dict]:
    return parse_csv(get(area_url(key, source, bbox, days, start)), source)


def fetch_range(key: str, source: str, bbox, first: date, last: date, get=http_get) -> list[dict]:
    """Every detection of a source in [first, last], in requests of at most 5 days."""
    out, d = [], first
    while d <= last:
        n = min(MAX_DAYS, (last - d).days + 1)
        out += fetch(key, source, bbox, n, d, get=get)
        d += timedelta(days=n)
    return out


def dumps(e: dict) -> str:
    return json.dumps(e, separators=(",", ":"))
