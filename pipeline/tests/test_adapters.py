import json

import pandas as pd
import pytest

from conftest import FIXTURES
from firecal.adapters import ADAPTERS, detect_format, get_adapter
from firecal.adapters.base import AdapterError, map_satellite, modis_confidence
from firecal.schema import validate

BINS = {"low": [0, 29], "nominal": [30, 79], "high": [80, 100]}


def run(fmt, path, **kw):
    return ADAPTERS[fmt](path, input_file=str(path), modis_bins=BINS, **{"source": None, **kw})


def test_archive_modis():
    df = run("firms_archive_csv", FIXTURES / "archive_modis.csv", source="MODIS_SP")
    validate(df)
    raw = pd.read_csv(FIXTURES / "archive_modis.csv", dtype=str)
    assert len(df) == len(raw)
    assert set(df.satellite) == {"Terra", "Aqua"} and set(df.sensor) == {"MODIS"}
    assert (df.source == "MODIS_SP").all() and (df.origin == "archive").all()
    assert df.country.eq("Lebanon").all()
    first = raw.iloc[0]
    assert df.datetime_utc[0] == pd.Timestamp(f"{first.acq_date} {first.acq_time[:2]}:{first.acq_time[2:]}", tz="UTC")
    assert df.fire_type.dtype == "Int8" and df.version[0] == raw.version[0]


def test_archive_viirs():
    df = run("firms_archive_csv", FIXTURES / "archive_viirs.csv")
    assert set(df.satellite) == {"SNPP"} and (df.source == "VIIRS_SNPP_SP").all()
    assert set(df.confidence_class) <= {"low", "nominal", "high"}


def test_api_unpadded_time():
    df = run("firms_api_csv", FIXTURES / "api_viirs.csv")
    assert df.datetime_utc[0] == pd.Timestamp("2025-07-05 00:21", tz="UTC")   # acq_time "21"
    assert df.datetime_utc[3] == pd.Timestamp("2025-07-01 11:15", tz="UTC")
    assert df.country.isna().all() and (df.origin == "api").all()
    assert df.confidence_class.tolist()[-1] == "low"


def test_nrt_without_type(tmp_path):
    raw = pd.read_csv(FIXTURES / "archive_modis.csv", dtype=str).drop(columns=["type", "country"])
    raw["version"] = "6.1NRT"
    f = tmp_path / "MODIS_C6_1_Global_24h.csv"
    raw.to_csv(f, index=False)
    assert detect_format(f) == "firms_nrt_csv"
    df = run("firms_nrt_csv", f, source="auto")
    assert df.fire_type.isna().all()
    assert (df.source == "MODIS_NRT").all() and (df.origin == "nrt").all()


def test_shapefile_uppercase_fields(tmp_path):
    import geopandas as gpd

    raw = pd.read_csv(FIXTURES / "archive_viirs.csv", dtype={"acq_time": str})
    raw["acq_date"] = pd.to_datetime(raw.acq_date)
    g = gpd.GeoDataFrame(raw.drop(columns=["country"]).rename(columns=str.upper),
                         geometry=gpd.points_from_xy(raw.longitude, raw.latitude), crs=4326)
    f = tmp_path / "fire_archive_SV-C2_1.shp"
    g.to_file(f)
    assert detect_format(f) == "shapefile"
    df = run("shapefile", f)
    assert len(df) == len(raw) and set(df.satellite) == {"SNPP"}
    assert df.datetime_utc[0] == pd.Timestamp(f"{raw.acq_date[0]:%Y-%m-%d} {raw.acq_time[0][:2]}:{raw.acq_time[0][2:]}", tz="UTC")


def test_json_records_and_geojson(tmp_path):
    raw = pd.read_csv(FIXTURES / "archive_modis.csv", dtype=str).drop(columns=["country"])
    recs = raw.to_dict("records")
    f1 = tmp_path / "fires.json"
    f1.write_text(json.dumps(recs))
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r["longitude"]), float(r["latitude"])]},
              "properties": {k: v for k, v in r.items() if k not in ("latitude", "longitude")}} for r in recs]
    f2 = tmp_path / "fires.geojson"
    f2.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    a, b = run("json", f1), run("json", f2)
    assert len(a) == len(b) == len(raw)
    pd.testing.assert_series_equal(a.lat, b.lat)
    assert (a.origin == "json").all()


def test_generic_column_map(tmp_path):
    raw = pd.read_csv(FIXTURES / "archive_viirs.csv", dtype=str)
    odd = raw.rename(columns={"latitude": "LAT_DD", "longitude": "LON_DD", "acq_date": "day", "acq_time": "hhmm",
                              "satellite": "sat", "confidence": "conf"}).drop(columns=["instrument"])
    f = tmp_path / "odd.csv"
    odd.to_csv(f, sep=";", index=False)
    df = run("generic", f, source="VIIRS_SNPP_SP", read={"sep": ";"},
             column_map={"latitude": "LAT_DD", "longitude": "LON_DD", "acq_date": "day", "acq_time": "hhmm",
                         "satellite": "sat", "confidence": "conf"})
    assert len(df) == len(raw) and set(df.sensor) == {"VIIRS"}


def test_detect_format_real_files():
    assert detect_format(FIXTURES / "archive_modis.csv") == "firms_archive_csv"
    assert detect_format(FIXTURES / "api_viirs.csv") == "firms_api_csv"
    assert get_adapter("auto", FIXTURES / "archive_viirs.csv")[0] == "firms_archive_csv"


def test_non_firms_csv_needs_generic(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("a,b\n1,2\n")
    with pytest.raises(AdapterError, match="generic"):
        detect_format(f)


@pytest.mark.parametrize("value,expected", [(0, "low"), (29, "low"), (30, "nominal"), (79, "nominal"),
                                            (80, "high"), (100, "high")])
def test_modis_confidence_bins(value, expected):
    assert modis_confidence(pd.Series([str(value)]), BINS)[0] == expected


@pytest.mark.parametrize("raw,sensor,expected", [("Terra", "MODIS", "Terra"), ("A", "MODIS", "Aqua"),
                                                 ("N", "VIIRS", "SNPP"), ("Suomi NPP", "VIIRS", "SNPP"),
                                                 ("N20", "VIIRS", "NOAA20"), ("N21", "VIIRS", "NOAA21")])
def test_satellite_map(raw, sensor, expected):
    assert map_satellite(pd.Series([raw]), pd.Series([sensor]))[0] == expected


def test_unknown_satellite_fails_loud():
    with pytest.raises(AdapterError, match="unknown satellite"):
        map_satellite(pd.Series(["Landsat"]), pd.Series(["VIIRS"]))
