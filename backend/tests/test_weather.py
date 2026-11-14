"""Weather client logic, without the network or a database."""

from datetime import date, datetime, timedelta

from firecal_api import weather as W

POINTS = [{"lat": 33.5, "lon": 35.5, "weight": 0.75}, {"lat": 34.2, "lon": 36.1, "weight": 0.25}]


def fake_meteomatics(url: str, creds=None) -> dict:
    """Answers like api.meteomatics.com: value depends on parameter, point and day (t_mean = month + lat/100)."""
    _, times, params, loc, _fmt = url.rsplit("/", 4)
    if "--" in times:
        a, rest = times.split("--")
        b = rest.split(":P")[0]
    else:
        a = b = times
    t0, t1 = (datetime.fromisoformat(x.replace("Z", "+00:00")).date() for x in (a, b))
    pts = [tuple(map(float, p.split(","))) for p in loc.split("+")]
    data = []
    for param in params.split(","):
        coords = []
        for lat, lon in pts:
            dates, t = [], t0
            while t <= t1:
                day = t - timedelta(days=1)
                v = {"t_mean_2m_24h:C": day.month + lat / 100, "t_max_2m_24h:C": day.month + 10,
                     "precip_24h:mm": 1.0, "wind_speed_mean_10m_24h:ms": 3.0,
                     "relative_humidity_mean_2m_24h:p": 50.0}[param]
                dates.append({"date": f"{t:%Y-%m-%d}T00:00:00Z", "value": v})
                t += timedelta(days=1)
            coords.append({"lat": round(lat, 6), "lon": round(lon, 6), "dates": dates})
        data.append({"parameter": param, "coordinates": coords})
    return {"version": "3.0", "status": "OK", "data": data}


def test_build_url_shifts_days_by_one():
    url = W.build_url(POINTS, ["t_mean_c", "precip_mm"], date(2020, 1, 1), date(2020, 12, 31))
    assert url == ("https://api.meteomatics.com/2020-01-02T00:00:00Z--2021-01-01T00:00:00Z:P1D/"
                   "t_mean_2m_24h:C,precip_24h:mm/33.5000,35.5000+34.2000,36.1000/json")


def test_parse_and_monthly():
    fields = list(W.FIELDS)
    body = fake_meteomatics(W.build_url(POINTS, fields, date(2020, 1, 1), date(2020, 2, 29)))
    daily = W.parse_daily(body, POINTS, fields)
    assert min(daily) == date(2020, 1, 1) and max(daily) == date(2020, 2, 29)
    months = W.to_monthly(daily, fields)
    jan = months[date(2020, 1, 1)]
    assert jan["n_days"] == 31
    assert jan["precip_mm"] == 31.0  # a monthly total
    assert abs(jan["t_mean_c"] - (1 + (0.75 * 33.5 + 0.25 * 34.2) / 100)) < 1e-9  # weighted over points
    assert months[date(2020, 2, 1)]["n_days"] == 29


def test_invalid_values_are_skipped():
    body = fake_meteomatics(W.build_url(POINTS[:1], ["precip_mm"], date(2020, 1, 1), date(2020, 1, 3)))
    body["data"][0]["coordinates"][0]["dates"][1]["value"] = -999
    months = W.to_monthly(W.parse_daily(body, POINTS[:1], ["precip_mm"]), ["precip_mm"])
    assert months[date(2020, 1, 1)] == {"n_days": 2, "precip_mm": 2.0}


def test_pick_points_one_per_tile_weighted():
    bbox = [35.0, 33.0, 36.5, 34.5]  # tiles 0.5° wide
    cells = [
        {"lat": 33.1, "lon": 35.1, "total": 10}, {"lat": 33.2, "lon": 35.2, "total": 30},  # same tile
        {"lat": 34.4, "lon": 36.4, "total": 60},
        {"lat": 34.0, "lon": 35.0, "total": 0},
    ]
    pts = W.pick_points(cells, bbox)
    assert pts == [{"lat": 34.4, "lon": 36.4, "weight": 0.6}, {"lat": 33.2, "lon": 35.2, "weight": 0.4}]
    assert len(W.pick_points([{"lat": 33 + i / 10, "lon": 35 + j / 10, "total": 1} for i in range(15) for j in range(15)],
                             bbox)) == 9


def test_months_to_fetch_and_chunks():
    today = date(2026, 11, 14)
    have = {date(2026, 1, 1): 31, date(2026, 10, 1): 30, date(2026, 9, 1): 29, date(2026, 8, 1): 20}
    todo = W.months_to_fetch(date(2025, 12, 1), date(2026, 12, 1), have, today)
    # Dec 2025 missing; Jan stored; Aug incomplete but old; Oct one day short and recent; Nov (13 days so far) missing.
    assert todo[0] == date(2025, 12, 1) and date(2026, 1, 1) not in todo and date(2026, 8, 1) not in todo
    assert date(2026, 10, 1) in todo and todo[-1] == date(2026, 11, 1) and date(2026, 12, 1) not in todo
    runs = W.chunks(todo, 4)
    assert date(2026, 9, 1) not in todo
    assert [len(r) for r in runs] == [1, 4, 2, 2]  # Dec | Feb-May | Jun-Jul | Oct-Nov


def test_anomalies():
    months = [{"ym": date(y, 7, 1), "n_days": 31, "complete": True, "t_mean_c": 25.0 + (y - 2001),
               "t_max_c": None, "precip_mm": 10.0, "wind_ms": 3.0, "rh_pct": 50.0} for y in range(2001, 2004)]
    months.append({"ym": date(2020, 7, 1), "n_days": 31, "complete": True, "t_mean_c": 29.0,
                   "t_max_c": None, "precip_mm": 2.0, "wind_ms": 3.0, "rh_pct": 50.0})
    months.append({"ym": date(2021, 7, 1), "n_days": 3, "complete": False, "t_mean_c": 30.0,
                   "t_max_c": None, "precip_mm": 0.0, "wind_ms": 3.0, "rh_pct": 50.0})
    out = W.with_anomalies(months, (2001, 2010))
    m = out[3]
    assert m["t_mean_c_normal"] == 26.0 and m["t_mean_c_anom"] == 3.0 and m["t_mean_c_z"] == 3.0
    assert m["precip_pct_of_normal"] == 20 and m["precip_mm_z"] is None  # no spread in the baseline
    assert m["t_max_c"] is None and m["t_max_c_normal"] is None
    assert out[4]["t_mean_c_anom"] is None and out[4]["precip_pct_of_normal"] is None  # incomplete month


class _LockConn:
    """Stands in for a connection whose weather lock is held by another fetch for the first `busy` tries."""

    def __init__(self, busy: int):
        self.busy, self.tries, self.unlocked = busy, 0, False

    async def fetchval(self, sql, *args):
        if "pg_try_advisory_lock" in sql:
            self.tries += 1
            return self.tries > self.busy
        return 0

    async def fetch(self, sql, *args):
        return []

    async def execute(self, sql, *args):
        if "pg_advisory_unlock" in sql:
            self.unlocked = True


def test_fetch_skips_when_locked_and_not_waiting():
    import asyncio

    conn, logs = _LockConn(busy=10**6), []
    assert asyncio.run(W.fetch_all(conn, None, None, [], log=logs.append)) == 0
    assert conn.tries == 1 and not conn.unlocked
    assert "skipping" in logs[-1]


def test_fetch_waits_for_the_lock(monkeypatch):
    import asyncio

    monkeypatch.setattr(W, "LOCK_RETRY_S", 0.01)
    conn, logs = _LockConn(busy=3), []
    assert asyncio.run(W.fetch_all(conn, None, None, [], log=logs.append, wait_lock=5)) == 0
    assert conn.tries == 4 and conn.unlocked
    assert "waiting" in logs[0] and not any("skipping" in m for m in logs)


def test_fetch_gives_up_after_waiting(monkeypatch):
    import asyncio

    monkeypatch.setattr(W, "LOCK_RETRY_S", 0.01)
    conn, logs = _LockConn(busy=10**6), []
    assert asyncio.run(W.fetch_all(conn, None, None, [], log=logs.append, wait_lock=0.05)) == 0
    assert conn.tries > 1 and not conn.unlocked
    assert "skipping" in logs[-1]
