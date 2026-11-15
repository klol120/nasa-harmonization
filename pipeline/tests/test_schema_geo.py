import numpy as np
import pandas as pd
import pytest

from conftest import FIXTURES
from firecal.adapters import ADAPTERS
from firecal.config import path
from firecal.geo import cell_bounds, cell_id, cell_index, tag_country
from firecal.schema import SchemaError, conform

BINS = {"low": [0, 29], "nominal": [30, 79], "high": [80, 100]}


@pytest.fixture
def detections():
    return ADAPTERS["firms_archive_csv"](FIXTURES / "archive_modis.csv", input_file="x", source="MODIS_SP",
                                        modis_bins=BINS)


def test_conform_rejects_missing_column(detections):
    with pytest.raises(SchemaError, match="missing"):
        conform(detections.drop(columns=["frp"]))


def test_conform_rejects_bad_category(detections):
    bad = detections.astype({"satellite": str})
    bad.loc[0, "satellite"] = "Landsat"
    with pytest.raises(SchemaError, match="satellite"):
        conform(bad)


def test_conform_rejects_nulls(detections):
    bad = detections.copy()
    bad.loc[0, "lat"] = np.nan
    with pytest.raises(SchemaError, match="nulls"):
        conform(bad)


def test_cell_edges_and_float_error():
    size = 0.05
    # 33.50 sits exactly on an edge; (33.50 + 90) / 0.05 = 2469.9999999999995 in floats
    assert cell_index([33.50], [35.0], size)[0][0] == 2470
    assert cell_id([33.5249], [35.0249], size)[0] == "2470_4300"
    assert cell_id([33.5251], [35.0251], size)[0] == "2470_4300"
    assert cell_id([-0.01], [-0.01], size)[0] == "1799_3599"


def test_cell_bounds_contain_point():
    rng = np.random.default_rng(0)
    lat, lon = rng.uniform(-60, 60, 500), rng.uniform(-170, 170, 500)
    for la, lo, cid in zip(lat, lon, cell_id(lat, lon, 0.05)):
        w, s, e, n = cell_bounds(cid, 0.05)
        assert w - 1e-9 <= lo < e + 1e-9 and s - 1e-9 <= la < n + 1e-9


def test_tag_country(cfg):
    lat = [33.89, 35.25, 35.17, 34.0, 33.6]
    lon = [35.50, 33.60, 33.36, 35.62, 34.0]   # Beirut, N. Cyprus, Nicosia (south), ~2 km off Lebanon, open sea
    got = tag_country(lat, lon, path(cfg, "boundaries"), max_sea_km=12).tolist()
    assert got[0] == "Lebanon"
    assert got[1] == "Northern Cyprus"
    assert got[2] in ("Cyprus", "Cyprus No Mans Area")
    assert got[3] == "Lebanon"
    assert pd.isna(got[4])
