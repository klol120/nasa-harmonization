"""Checks that need only the export files (no database)."""

import json

import pytest

from firecal_api import aggregate as A
from firecal_api import contract as C
from firecal_api.ingest import parse_cells, parse_region_monthly, parse_series, read_meta

from .conftest import EXPORT_DIR, LEBANON


def test_cell_ids():
    assert C.cell_rc(33.075, 35.125) == (2461, 4302)
    assert C.cell_id(2461, 4302) == "2461_4302"
    assert C.parse_cell_id("2461_4302") == (2461, 4302)
    assert C.cell_key(2461, 4302) == 2461 * 7200 + 4302


def test_month_range():
    ms = C.month_range(C.parse_ym("2000-11"), C.parse_ym("2001-02"))
    assert [C.ym_str(m) for m in ms] == ["2000-11", "2000-12", "2001-01", "2001-02"]


def test_point_in_polygon_with_hole():
    outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    assert A.point_in_polygon(1, 1, [outer, hole])
    assert not A.point_in_polygon(5, 5, [outer, hole])
    assert not A.point_in_polygon(11, 5, [outer])


@pytest.mark.parametrize("region", ["lebanon", "greece", "eastmed"])
def test_export_files_parse(region):
    folder = EXPORT_DIR / region
    if not folder.is_dir():
        pytest.skip(f"{region} not exported")
    warnings = []
    meta = read_meta(folder, warnings)
    months = parse_region_monthly(folder, meta, warnings)
    cells, members = parse_cells(folder, meta)
    assert len(cells) == meta["n_cells"]
    assert len(months) == len(C.month_range(C.parse_ym(meta["time"]["first_month"]), C.parse_ym(meta["time"]["last_month"])))


@pytest.mark.parametrize("region", ["lebanon", "greece", "eastmed"])
def test_z_recompute_matches_export(region):
    """The aggregation z formula reproduces the exported region z (so it is the contract's method)."""
    folder = EXPORT_DIR / region
    meta = json.loads((folder / "meta.json").read_text())
    rows = json.loads((folder / "region_monthly.json").read_text())
    months = [{"ym": C.parse_ym(r["ym"]), "data_available": r["data_available"], "display_only": r["display_only"]} for r in rows]
    sums = {C.parse_ym(r["ym"]): r["harmonized"] for r in rows}
    z = A.anomaly_z(months, sums, tuple(meta["anomalies"]["baseline_years"]))
    for r in rows:
        got = z[C.parse_ym(r["ym"])]
        if r["anomaly_z"] is None:
            assert got is None, r["ym"]
        else:
            assert got == pytest.approx(r["anomaly_z"], abs=2e-4), r["ym"]


def test_series_parse_lebanon():
    meta = json.loads((LEBANON / "meta.json").read_text())
    rows, listed = parse_series(LEBANON, meta)
    assert set(listed) == set(range(2000, 2027))
    assert rows
