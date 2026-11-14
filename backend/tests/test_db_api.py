"""Load the Lebanon export into a throwaway <name>_test database and check the API against the files."""

import asyncio
import json
import shutil

import asyncpg
import pytest

from firecal_api import contract as C
from firecal_api.contract import ContractError

from .conftest import LEBANON, TEST_DB_URL

pytestmark = pytest.mark.db


def run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    from firecal_api.db import connect, ensure_database, migrate

    await ensure_database(TEST_DB_URL)
    conn = await connect(TEST_DB_URL)
    await conn.execute("drop schema public cascade; create schema public")
    await migrate(conn)
    return conn


@pytest.fixture(scope="module")
def loaded():
    from firecal_api.ingest import ingest_region

    async def go():
        conn = await _fresh_db()
        try:
            rep = await ingest_region(conn, LEBANON, log=lambda *_: None)
        finally:
            await conn.close()
        return rep

    return run(go())


@pytest.fixture(scope="module")
def client(loaded):
    from fastapi.testclient import TestClient

    from firecal_api.api import app

    with TestClient(app) as c:
        yield c


def _meta():
    return json.loads((LEBANON / "meta.json").read_text())


def test_ingest_counts(loaded):
    meta = json.loads((LEBANON / "meta.json").read_text())
    assert loaded.n_cells == meta["n_cells"]
    assert loaded.n_cell_months == loaded.n_cells * loaded.n_months
    assert loaded.n_series_files == 27


def test_reingest_same_export_is_skipped(loaded):
    from firecal_api.db import connect
    from firecal_api.ingest import ingest_region

    async def go():
        conn = await connect(TEST_DB_URL)
        try:
            return await ingest_region(conn, LEBANON, check_series=False, log=lambda *_: None)
        finally:
            await conn.close()

    rep = run(go())
    assert rep.skipped and rep.release_id == loaded.release_id


def test_regions(client):
    rs = client.get("/regions").json()
    assert [r["region"] for r in rs] == ["lebanon"]
    assert rs[0]["baseline_years"] == [2012, 2025]


def test_monthly_equals_file(client):
    got = client.get("/regions/lebanon/monthly").json()
    want = json.loads((LEBANON / "region_monthly.json").read_text())
    assert got == want


def test_cells_equal_file(client):
    got = client.get("/regions/lebanon/cells").json()
    want = json.loads((LEBANON / "cells.geojson").read_text())
    by_id = {f["properties"]["cell_id"]: f for f in want["features"]}
    assert len(got["features"]) == len(by_id)
    for f in got["features"]:
        w = by_id[f["properties"]["cell_id"]]
        assert f["properties"] == w["properties"]
        flat = lambda g: [v for pt in g["coordinates"][0] for v in pt]  # noqa: E731
        assert flat(f["geometry"]) == pytest.approx(flat(w["geometry"]))


@pytest.mark.parametrize("year", [2000, 2007, 2011, 2012, 2019, 2026])
def test_series_equals_file(client, year):
    got = client.get(f"/regions/lebanon/series/{year}").json()
    want = json.loads((LEBANON / "cells_series" / f"{year}.json").read_text())
    assert got["ym"] == want["ym"] and got["fields"] == want["fields"]
    assert set(got["cells"]) == set(want["cells"])
    for cid, s in want["cells"].items():
        assert got["cells"][cid] == s, cid


def test_aggregate_whole_region_reproduces_region_monthly(client):
    got = client.post("/regions/lebanon/aggregate", json={}).json()
    want = json.loads((LEBANON / "region_monthly.json").read_text())
    assert got["n_cells"] == _meta()["n_cells"]
    for g, w in zip(got["months"], want, strict=True):
        assert g["ym"] == w["ym"]
        assert g["modis_raw"] == w["modis_raw"] and g["viirs_raw"] == w["viirs_raw"]
        assert g.get("noaa20_raw") == w.get("noaa20_raw") and g.get("source") == w.get("source")
        for f in ("harmonized", "harmonized_low", "harmonized_high"):
            assert (g[f] is None) == (w[f] is None)
            if w[f] is not None:
                assert g[f] == pytest.approx(w[f], abs=0.05)
        if w["anomaly_z"] is None:
            assert g["anomaly_z"] is None
        else:
            assert g["anomaly_z"] == pytest.approx(w["anomaly_z"], abs=2e-3)
        assert all(g[f] == w[f] for f in C.REGION_MONTH_FLAGS)


def test_aggregate_area_and_persistent(client):
    full = client.post("/regions/lebanon/aggregate", json={}).json()
    nop = client.post("/regions/lebanon/aggregate", json={"exclude_persistent": True}).json()
    meta = _meta()
    assert nop["n_cells"] == meta["n_cells"] - meta["n_persistent_cells"]
    box = client.post("/regions/lebanon/aggregate", json={"bbox": [35.4, 33.55, 35.75, 33.8], "from": "2019-01", "to": "2019-12"}).json()
    assert 0 < box["n_cells"] < meta["n_cells"] and len(box["months"]) == 12
    poly = [[[35.4, 33.55], [35.75, 33.55], [35.75, 33.8], [35.4, 33.8], [35.4, 33.55]]]
    assert client.post("/regions/lebanon/aggregate", json={"polygon": poly}).json()["n_cells"] == box["n_cells"]
    assert sum(m["modis_raw"] or 0 for m in nop["months"]) <= sum(m["modis_raw"] or 0 for m in full["months"])
    assert client.post("/regions/lebanon/aggregate", json={"bbox": [0, 0, 1, 1]}).status_code == 404


def test_calendar(client):
    rows = client.get("/regions/lebanon/calendar", params={"cell_id": "2461_4303", "from": "2007-01", "to": "2007-12"}).json()
    assert len(rows) == 12 and rows[8]["harmonized"] == pytest.approx(0.17, abs=0.006)
    assert client.get("/regions/lebanon/calendar").status_code == 413
    csv_text = client.get("/regions/lebanon/calendar", params={"format": "csv", "from": "2020-01", "to": "2020-01"}).text
    lines = csv_text.strip().split("\n")
    assert lines[0] == ",".join(C.CALENDAR_FIELDS) and len(lines) == 1 + _meta()["n_cells"]


def test_predictions_roundtrip(client, loaded):
    from firecal_api.db import connect
    from firecal_api.ml import save_run

    async def go():
        conn = await connect(TEST_DB_URL)
        try:
            return await save_run(
                conn, region="lebanon", model_name="test-model", model_version="0",
                region_predictions=[("2026-08", 120.5, 90.0, 150.0)],
                cell_predictions=[("2461_4303", "2026-08", 0.4, None, None)],
                metrics={"mae": 1.0},
            )
        finally:
            await conn.close()

    run_id = run(go())
    r = client.get("/regions/lebanon/predictions").json()
    assert r["run_id"] == run_id and r["months"] == [{"ym": "2026-08", "value": 120.5, "value_low": 90.0, "value_high": 150.0}]
    c = client.get("/regions/lebanon/predictions", params={"level": "cell"}).json()
    assert c["rows"][0]["cell_id"] == "2461_4303"


def test_broken_export_is_rejected_and_nothing_loaded(tmp_path, loaded):
    """A contract violation rolls the whole load back."""
    from firecal_api.db import connect
    from firecal_api.ingest import ingest_region

    bad = tmp_path / "lebanon"
    shutil.copytree(LEBANON, bad)
    rows = json.loads((bad / "region_monthly.json").read_text())
    rows[-1]["data_available"] = True  # 2026-12 has no data, so harmonized is null: violates "null iff"
    (bad / "region_monthly.json").write_text(json.dumps(rows))

    async def go():
        conn = await connect(TEST_DB_URL)
        try:
            before = await conn.fetchval("select count(*) from release")
            with pytest.raises(ContractError, match="null iff"):
                await ingest_region(conn, bad, check_series=False, force=True, log=lambda *_: None)
            return before, await conn.fetchval("select count(*) from release")
        finally:
            await conn.close()

    before, after = run(go())
    assert before == after


def test_csv_only_export_loads(tmp_path, loaded):
    """Without calendar.parquet the CSV is used (values rounded to 3 decimals, still within the checks)."""
    from firecal_api.db import connect
    from firecal_api.ingest import ingest_region

    csv_only = tmp_path / "lebanon"
    shutil.copytree(LEBANON, csv_only)
    (csv_only / "calendar.parquet").unlink()

    async def go():
        conn = await connect(TEST_DB_URL)
        try:
            rep = await ingest_region(conn, csv_only, force=True, make_current=False, log=lambda *_: None)
            await conn.execute("delete from release where release_id = $1", rep.release_id)
            return rep
        finally:
            await conn.close()

    rep = run(go())
    assert rep.n_cell_months == loaded.n_cell_months


def test_noaa20_continuation(client):
    """v0.5: the switch month carries source and noaa20_raw, and NOAA-20 harmonized is c_m x noaa20_raw."""
    meta = _meta()
    if meta["contract_version"] == "0.4":
        pytest.skip("v0.4 export has no NOAA-20 fields")
    rows = {r["ym"]: r for r in client.get("/regions/lebanon/monthly").json()}
    switch = meta["time"]["viirs_switch_date"][:7]
    assert rows[switch]["source"] == "SNPP+NOAA20"
    assert rows["2011-12"]["source"] == "MODIS" and rows["2012-01"]["source"] == "MODIS+SNPP" and rows["2019-10"]["source"] == "SNPP"
    assert rows["2017-01"]["noaa20_raw"] is None and rows["2019-01"]["noaa20_raw"] is not None
    for r in rows.values():
        assert (r["source"] is None) == (not r["data_available"])
    cal = client.get("/regions/lebanon/calendar", params={"from": switch, "to": switch}).json()
    assert sum(x["noaa20_raw"] or 0 for x in cal) == rows[switch]["noaa20_raw"]
