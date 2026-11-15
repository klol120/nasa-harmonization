"""Live pipeline: the pure logic, then one pass through a throwaway database."""

import asyncio
import json
from datetime import date, datetime, timezone

import pytest

from firecal_api import contract as C
from firecal_api.live import consumer as LC
from firecal_api.live import eventhub as EH
from firecal_api.live import firms as F
from firecal_api.live import harmonize as H
from firecal_api.live import poller as P
from firecal_api.live import replay as R
from firecal_api.live import store as S

from .conftest import LEBANON, TEST_DB_URL

CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
33.5512,35.6021,330.5,0.4,0.4,2026-11-13,52,N20,VIIRS,n,2.0NRT,290.1,2.1,N
33.5513,35.6022,331.0,0.4,0.4,2026-11-13,1030,N20,VIIRS,h,2.0NRT,291.0,5.5,D
bad,row,,,,2026-11-13,x,N20,VIIRS,n,2.0NRT,,,
"""


def test_area_url_and_limits():
    u = F.area_url("KEY", "VIIRS_NOAA20_NRT", [30.0, 29.4, 42.4, 38.0], 2)
    assert u.endswith("/KEY/VIIRS_NOAA20_NRT/30,29.4,42.4,38/2")
    assert F.area_url("KEY", "VIIRS_SNPP_SP", [1, 2, 3, 4], 5, date(2021, 8, 3)).endswith("/5/2021-08-03")
    with pytest.raises(ValueError):
        F.area_url("KEY", "VIIRS_NOAA20_NRT", [1, 2, 3, 4], 6)
    with pytest.raises(ValueError):
        F.area_url("KEY", "NOPE", [1, 2, 3, 4], 1)


def test_parse_csv_to_events():
    ev = F.parse_csv(CSV, "VIIRS_NOAA20_NRT")
    assert len(ev) == 2  # the unreadable row is skipped
    e = ev[0]
    assert e["sensor"] == "NOAA20" and e["acq"] == "2026-11-13T00:52:00Z" and e["confidence"] == "n" and e["frp"] == 2.1
    assert e["id"] != ev[1]["id"] and e["id"] == F.parse_csv(CSV, "VIIRS_NOAA20_NRT")[0]["id"]  # stable ids
    assert F.parse_csv("", "VIIRS_NOAA20_NRT") == []
    with pytest.raises(F.FirmsError):
        F.parse_csv("Invalid MAP_KEY.", "VIIRS_NOAA20_NRT")


def test_event_row_uses_the_contract_grid():
    e = F.parse_csv(CSV, "VIIRS_NOAA20_NRT")[0]
    row = F.event_row(json.loads(F.dumps(e)))
    r, c = C.cell_rc(33.5512, 35.6021)
    assert row[6] == date(2026, 11, 13) and row[7] == C.cell_key(r, c) and row[11] is False
    with pytest.raises(ValueError):
        F.event_row({**e, "lat": 123})


def test_fire_days_follow_the_pipeline_rules():
    d1, d2 = date(2026, 11, 2), date(2026, 11, 3)  # S-NPP's last day, NOAA-20's first
    p = (33.5, 35.5)
    rows = [
        (1, d1, "SNPP", "n", False, *p), (1, d1, "SNPP", "h", False, *p),  # same cell-day twice: one fire-day
        (1, d1, "NOAA20", "n", False, *p),                                 # before the switch: raw count only
        (1, d2, "NOAA20", "h", False, *p),
        (1, d2, "SNPP", "n", False, *p),                                   # S-NPP after the switch: not counted
        (2, d2, "NOAA20", "l", False, *p),                                 # low confidence: dropped
        (2, d2, "NOAA21", "n", False, *p),                                 # NOAA-21 is not used
        (3, d2, "SNPP", "n", True, *p),                                    # simulated
    ]
    rules = H.Rules("lebanon")
    assert rules.switch_date == d2 and rules.factor_source.startswith("frozen")
    assert rules.fire_days(rows, include_simulated=False) == {1: {"SNPP": 1, "NOAA20": 1, "NOAA20_all": 2}}
    assert rules.fire_days(rows, include_simulated=True)[3] == {"SIM": 1}
    # S-NPP counts as it is, NOAA-20 times c (Lebanon: 0.9278, band 0.8825-0.9664).
    h, lo, hi = rules.to_snpp_equivalent({"SNPP": 1, "NOAA20": 1, "NOAA20_all": 2}, 11)
    assert (round(h, 4), round(lo, 4), round(hi, 4)) == (1.9278, 1.8825, 1.9664)


def test_rules_prefer_the_factors_of_the_release():
    meta = {"calibration": {"continuation": {"switch_date": "2026-11-03",
                                             "factors": [{"month": m, "c": 0.5, "c_low": 0.4, "c_high": 0.6} for m in range(1, 13)]}}}
    r = H.Rules("lebanon", meta)
    assert r.factor_source == "release" and r.factor("NOAA20", 3) == (0.5, 0.4, 0.6) and r.factor("SNPP", 3) == (1.0, 1.0, 1.0)
    # A region with no calibration at all: factor 1, marked provisional.
    unknown = H.Rules("atlantis")
    assert unknown.factor("NOAA20", 1) == (1.0, 1.0, 1.0) and unknown.provisional


def test_static_source_cells_are_dropped(monkeypatch):
    lat, lon = 33.905, 35.505
    monkeypatch.setattr(H, "excluded_cells", lambda region: frozenset({H.fine_key(lat, lon)}))
    rules = H.Rules("lebanon")
    assert not rules.keep("n", lat, lon) and rules.keep("n", lat + 0.02, lon) and not rules.keep("l", lat + 0.02, lon)


def test_eventhub_token_and_batches():
    hub = EH.parse_connection("Endpoint=sb://ns.servicebus.windows.net/;SharedAccessKeyName=send;SharedAccessKey=abc=;EntityPath=detections")
    assert hub.url == "https://ns.servicebus.windows.net/detections" and hub.key == "abc="
    t = EH.sas_token(hub, ttl=60, now=1000)
    assert t.startswith("SharedAccessSignature sr=https%3A%2F%2Fns.servicebus.windows.net%2Fdetections&sig=") and "&se=1060&skn=send" in t
    chunks = list(EH.batches(["x" * 100] * 25, max_bytes=1000))
    assert sum(map(len, chunks)) == 25 and all(sum(len(b) + 16 for b in c) <= 1000 for c in chunks)
    with pytest.raises(EH.EventHubError):
        EH.parse_connection("Endpoint=sb://ns.servicebus.windows.net/;SharedAccessKeyName=send")


def test_poll_boxes_and_backfill_plan():
    rels = [{"bbox": [35.0, 33.0, 36.7, 34.7]}, {"bbox": [30.0, 29.4, 42.4, 38.0]}, {"bbox": [19.2, 34.7, 29.8, 41.8]}]
    assert P.poll_boxes(rels) == [[30.0, 29.4, 42.4, 38.0], [19.2, 34.7, 29.8, 41.8]]  # Lebanon lies inside EastMed
    plan = P.backfill_plan(date(2026, 8, 1), date(2026, 11, 14))
    assert plan[0] == ("VIIRS_SNPP_NRT", date(2026, 8, 1), H.SNPP_LAST_DAY)
    assert [p[0] for p in P.backfill_plan(date(2026, 11, 5), date(2026, 11, 14))] == ["VIIRS_NOAA20_NRT"]


def test_replay_moves_the_outbreak_to_today():
    acq = datetime(2021, 8, 12, 11, 0, tzinfo=timezone.utc)
    src = [F.event("SNPP", "VIIRS_SNPP_SP", 38.8, 23.3, acq), F.event("SNPP", "VIIRS_SNPP_SP", 38.8, 23.3, acq.replace(day=3))]
    out = R.shift_events(src, date(2021, 8, 12), date(2026, 11, 5))
    assert [e["acq"][:10] for e in out] == ["2026-11-05"]  # the 3rd would land in October: dropped
    assert out[0]["simulated"] and out[0]["sensor"] == "SIM" and out[0]["id"].startswith("sim-")


def test_overlay_replaces_a_month_with_its_live_version():
    lv = {"viirs_raw": 0, "noaa20_raw": 6, "harmonized": 5.5668, "harmonized_low": 5.295, "harmonized_high": 5.7984,
          "anomaly_z": -0.98765, "partial_month": True, "through": date(2026, 11, 14), "sensors": {"NOAA20": 6},
          "harmonization": H.VERSION, "provisional": False}
    empty = {"ym": date(2026, 11, 1), "viirs_raw": None, "harmonized": None, "data_available": False, "partial_month": False}
    m = S.overlay_month(empty, lv)
    assert m["live"] and m["data_available"] and m["harmonized"] == 5.5668 and m["anomaly_z"] == -0.9877 and m["live_through"] == "2026-11-14"
    assert m["source"] == "NOAA20" and m["noaa20_raw"] == 6 and m["live_provisional"] is False
    assert S.overlay_month(empty, None) is empty


# ---------------------------------------------------------------- with a database


@pytest.mark.db
def test_stream_to_api_roundtrip():
    """Events -> consumer -> live months -> API, on the Lebanon export."""
    from fastapi.testclient import TestClient

    from firecal_api.db import connect, ensure_database, migrate
    from firecal_api.ingest import ingest_region

    async def prepare():
        await ensure_database(TEST_DB_URL)
        conn = await connect(TEST_DB_URL)
        try:
            await conn.execute("drop schema public cascade; create schema public")
            await migrate(conn)
            await ingest_region(conn, LEBANON, log=lambda *_: None)
            rel = (await S.current_releases(conn))[0]
            first = S.live_first_month(rel)
            # Two cells in the middle of the country: border cells can have their centre outside the footprint.
            w, so, e, n = rel["bbox"]
            cells = await conn.fetch(
                """select c.lat_center, c.lon_center, c.cell_id from release_cell rc join cell c using (cell_key)
                   where rc.release_id = $1 order by abs(c.lat_center - $2) + abs(c.lon_center - $3), c.cell_key limit 2""",
                rel["release_id"], (so + n) / 2, (w + e) / 2,
            )
            (lat, lon, cid), (lat2, lon2, _) = (tuple(r) for r in cells)
            t = datetime(first.year, first.month, 5, 10, 0, tzinfo=timezone.utc)
            # The satellite the pipeline counts those days from, and what two of its fire-days are worth.
            rules = H.Rules("lebanon", rel["meta"])
            (sat,) = rules.sensors_for_day(t.date())
            src = f"VIIRS_{sat}_NRT"
            expect = round(2 * rules.factor(sat, first.month)[0], 4)
            events = [
                F.event(sat, src, lat, lon, t, confidence="n"),
                F.event(sat, src, lat, lon, t.replace(hour=22), confidence="h"),   # same cell-day
                F.event(sat, src, lat, lon, t.replace(day=6), confidence="n"),
                F.event(sat, src, lat, lon, t.replace(day=7), confidence="l"),     # low confidence: dropped
                F.event(sat, src, 0.0, 0.0, t),                                    # outside the region
                F.event("SIM", "replay:test", lat2, lon2, t, simulated=True),
                F.coverage_event(S.month_end(first), [src]),
                {"type": "detection", "id": "broken"},
            ]
            r1 = await LC.process(conn, events)
            r2 = await LC.process(conn, events)  # the same batch again changes nothing
            return rel["release_id"], first, cid, r1, r2, sat, expect
        finally:
            await conn.close()

    rid, first, cid, r1, r2, sat, expect = asyncio.run(prepare())
    assert r1["new"] == 6 and r1["unreadable"] == 1 and r1["months_rebuilt"] == 2  # real + demo month
    assert r2["new"] == 0 and r2["months_rebuilt"] == 0
    ym = C.ym_str(first)

    from firecal_api.api import app

    with TestClient(app) as client:
        base = {m["ym"]: m for m in client.get("/regions/lebanon/monthly").json()}
        assert "live" not in base[ym]  # without live=1: the release as exported

        # The month the release covers only in part is rebuilt whole from the live detections.
        live = {m["ym"]: m for m in client.get("/regions/lebanon/monthly?live=1").json()}
        assert live[ym]["live"] and round(live[ym]["harmonized"], 4) == expect and not live[ym]["partial_month"]
        assert live[ym]["source"] == sat and live[ym]["viirs_raw" if sat == "SNPP" else "noaa20_raw"] == 2
        prev = C.ym_str(date(first.year, first.month - 1, 1))
        assert live[prev] == base[prev]  # months the release covers are untouched

        demo = {m["ym"]: m for m in client.get("/regions/lebanon/monthly?live=1&demo=1").json()}
        assert round(demo[ym]["harmonized"], 4) == round(expect + 1, 4)

        s = client.get(f"/regions/lebanon/series/{first.year}?live=1").json()
        i = s["ym"].index(ym)
        assert s["cells"][cid]["h"][i] == round(expect, 2)
        pinned = client.get(f"/regions/lebanon/series/{first.year}?release={rid}").json()
        assert pinned["cells"].get(cid, {"h": [None] * 12})["h"][i] != round(expect, 2)  # without live=1: as exported

        agg = client.post("/regions/lebanon/aggregate?live=1", json={"cell_ids": [cid]}).json()
        row = next(m for m in agg["months"] if m["ym"] == ym)
        assert row["harmonized"] == expect and row["live"] and row["data_available"]

        cal = client.get(f"/regions/lebanon/calendar?live=1&cell_id={cid}&from={ym}&to={ym}").json()
        assert cal[0]["harmonized"] == expect and cal[0]["noaa20_raw" if sat == "NOAA20" else "viirs_raw"] == 2

        st = client.get("/regions/lebanon/live?points=10").json()
        assert st["enabled"] and st["first_month"] == ym and st["demo_available"]
        assert st["harmonization"]["version"] == H.VERSION


def test_poll_catches_up_from_the_last_covered_day(monkeypatch):
    """A slow schedule (say monthly) still reads every day since the last poll, in 5-day requests."""
    from datetime import timedelta

    today = datetime.now(timezone.utc).date()
    urls, sent = [], []

    async def fake(*a, **k):
        return None

    async def go():
        monkeypatch.setattr(S, "current_releases", lambda conn, regions=None: _async([{"bbox": [35.0, 33.0, 36.7, 34.7]}]))
        monkeypatch.setattr(S, "get_coverage", lambda conn: _async(today - timedelta(days=30)))
        monkeypatch.setattr(S, "known_ids", lambda conn, ids: _async(set()))
        monkeypatch.setattr(S, "set_state", fake)
        return await P.poll(None, "KEY", sent.extend, get=lambda url: urls.append(url) or CSV, log=lambda m: None)

    out = asyncio.run(go())
    assert out["from"] == (today - timedelta(days=31)).isoformat()
    assert len(urls) == 7 and all("/VIIRS_NOAA20_NRT/" in u for u in urls)  # 32 days in requests of <= 5
    assert sent[-1]["type"] == "coverage" and sent[-1]["through"] == today.isoformat() and out["new"] == 2


async def _async(v):
    return v
