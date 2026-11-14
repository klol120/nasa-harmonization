"""The export matches docs/data_contract.md (synthetic region, full pipeline)."""
import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from firecal.config import load_config
from firecal.io import read_stage
from firecal.stages import anomalies, calibrate, clean, export, grid, ingest, splice, terra, validate
from firecal.stages.export import CALENDAR_COLUMNS
from synthetic import SynthSpec, config_overrides, write_csvs


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("export")
    spec = SynthSpec(seed=21, start=dt.date(2000, 11, 1), end=dt.date(2020, 12, 31), n_rows=10, n_cols=10)
    write_csvs(spec, tmp / "raw")
    ov = config_overrides(spec, tmp)
    ov["calibration"] = {"strategies": ["single", "local"], "strategy": "local", "bootstrap": {"n": 200}}
    ov["terra"] = {"strategies": ["single", "local"], "strategy": "local"}
    ov["years"] = {"stats_last_year": 2019, "display_last_month": "2021-03"}   # 2020 display-only, 2021 no data
    ov["anomalies"] = {"baseline_years": [2001, 2019], "sensitivity_baselines": [[2012, 2019]], "min_sd": 0}
    cfg = load_config(overrides=ov)
    for stage in (ingest, clean, grid, terra, calibrate, validate, splice, anomalies, export):
        stage.run(cfg, "synth")
    d = tmp / "export" / "synth"
    return cfg, spec, d, pd.read_parquet(d / "calendar.parquet")


def regional(d, cal):
    """Calendar rows joined to the region-month flags (contract 0.4 keeps flags in region_monthly)."""
    r = pd.read_csv(d / "region_monthly.csv")
    return cal.merge(r[["ym", "is_estimate", "has_gap", "data_available", "partial_month", "display_only",
                        "low_confidence"]], on="ym", how="left")


def test_files_exist(exported):
    _, _, d, _ = exported
    for f in ("calendar.parquet", "calendar.csv.gz", "region_monthly.csv", "region_monthly.json",
              "cells.geojson", "meta.json", "cells_series/2005.json"):
        assert (d / f).stat().st_size > 0, f
    assert not (d / "cells.json").exists()        # dropped in 0.4


def test_calendar_columns_and_types(exported):
    _, _, _, cal = exported
    assert list(cal.columns) == list(CALENDAR_COLUMNS)
    for c, t in CALENDAR_COLUMNS.items():
        assert str(cal[c].dtype) == str(pd.Series(dtype=t).dtype), c
    assert not cal.duplicated(["cell_id", "year", "month"]).any()
    assert (cal.ym == cal.year.astype(str) + "-" + cal.month.astype(int).astype(str).str.zfill(2)).all()
    for flag in ("is_estimate", "low_confidence", "data_available", "is_persistent"):
        assert flag not in cal.columns


def test_every_cell_has_every_month(exported):
    _, _, _, cal = exported
    n_months = (2021 - 2000) * 12 + 3 - 10        # 2000-11 .. 2021-03
    assert (cal.groupby("cell_id").size() == n_months).all()


def test_invariants(exported):
    _, _, d, cal = exported
    cal = regional(d, cal)
    assert cal.data_available.notna().all()                                        # every month has flags
    v = cal.harmonized.notna()
    assert (cal.harmonized.isna() == ~cal.data_available).all()
    assert ((cal.harmonized_low <= cal.harmonized + 1e-4) & (cal.harmonized <= cal.harmonized_high + 1e-4))[v].all()
    obs = ~cal.is_estimate & v
    assert (cal.harmonized[obs] == cal.viirs_raw[obs].astype("float32")).all()
    assert (cal.harmonized_low[obs] == cal.harmonized[obs]).all()
    assert cal.anomaly_z[~cal.data_available].isna().all()
    assert (cal.display_only == (cal.year > 2019)).all()


def test_no_data_months_are_null_not_zero(exported):
    _, _, d, cal = exported
    cal = regional(d, cal)
    late = cal[cal.year == 2021]
    assert not late.data_available.any()
    assert late.harmonized.isna().all() and late.modis_raw.isna().all() and late.viirs_raw.isna().all()
    assert cal[cal.year < 2012].viirs_raw.isna().all()


def test_cells_series_matches_calendar(exported):
    _, _, d, cal = exported
    reg = pd.read_csv(d / "region_monthly.csv")
    for year in (2005, 2016, 2021):
        doc = json.loads((d / "cells_series" / f"{year}.json").read_text())
        months = reg[reg.year == year].sort_values("month")
        assert doc["ym"] == months.ym.tolist()
        c = cal[cal.year == year]
        for cid, g in c.groupby("cell_id", observed=True):
            g = g.sort_values("month")
            if cid not in doc["cells"]:                       # omitted: no fire-days this year
                assert (g.harmonized.fillna(0) == 0).all() and (g.modis_raw.fillna(0) == 0).all()
                continue
            got = doc["cells"][cid]
            exp_h = [None if pd.isna(x) else round(float(x), 2) for x in g.harmonized]
            assert got["h"] == exp_h
            assert got["m"] == [None if pd.isna(x) else int(x) for x in g.modis_raw]


def test_estimates_before_splice_only(exported):
    _, _, d, cal = exported
    cal = regional(d, cal)
    assert cal[cal.year <= 2011].is_estimate.all()
    assert cal[(cal.year == 2012) & (cal.month == 1)].is_estimate.all()            # mixed month
    assert not cal[(cal.year > 2012) | ((cal.year == 2012) & (cal.month > 1))].is_estimate.any()
    assert not cal[cal.low_confidence & ~cal.is_estimate].shape[0]


def test_january_2012_is_estimate_plus_observed(exported):
    cfg, _, _, cal = exported
    fac = read_stage(cfg, "synth", "factors").query("strategy == 'local'").set_index("month").a
    fs = read_stage(cfg, "synth", "fire_segments")
    j = fs[(fs.year == 2012) & (fs.month == 1)]
    expected = fac[1] * j[j.seg == 0].n_modis.sum() + j[j.seg == 1].n_viirs.sum()
    got = cal[(cal.year == 2012) & (cal.month == 1)].harmonized.sum()
    assert got == pytest.approx(expected, rel=1e-5)


def test_terra_only_months_use_kT(exported):
    cfg, _, _, cal = exported
    fac = read_stage(cfg, "synth", "factors").query("strategy == 'local'").set_index("month").a
    kt = read_stage(cfg, "synth", "kT").query("strategy == 'local'").set_index("month").kT
    fs = read_stage(cfg, "synth", "fire_segments")
    m = fs[(fs.year == 2001) & (fs.month == 9)].n_modis.sum()
    got = cal[(cal.year == 2001) & (cal.month == 9)].harmonized.sum()
    assert got == pytest.approx(m * fac[9] * kt[9], rel=1e-5)


def test_region_monthly_matches_cell_sums(exported):
    _, _, d, cal = exported
    r = pd.read_csv(d / "region_monthly.csv")
    s = cal.groupby(["year", "month"]).harmonized.sum(min_count=1).reset_index()
    m = r.merge(s, on=["year", "month"], suffixes=("", "_cells"))
    ok = m.harmonized.notna()
    assert np.allclose(m.harmonized[ok], m.harmonized_cells[ok], rtol=1e-4)
    assert (m.harmonized.isna() == ~m.data_available).all()
    j = json.loads((d / "region_monthly.json").read_text())
    assert len(j) == len(r) and set(j[0]) == set(r.columns)


def test_area_anomaly_recomputed_from_sums(exported):
    """Contract: an area's z comes from the summed series, as in region_monthly."""
    _, _, d, cal = exported
    r = pd.read_csv(d / "region_monthly.csv")
    base = r[r.year.between(2001, 2019) & r.data_available & ~r.display_only]
    st = base.groupby("month").harmonized.agg(["mean", "std"])
    z = (r.harmonized - r.month.map(st["mean"])) / r.month.map(st["std"])
    ok = r.anomaly_z.notna()
    assert np.allclose(z[ok], r.anomaly_z[ok], atol=1e-3)
    summed_cell_z = cal.groupby(["year", "month"]).anomaly_z.sum().reset_index()
    assert not np.allclose(summed_cell_z.anomaly_z.to_numpy()[: ok.sum()], r.anomaly_z[ok].to_numpy())


def test_cells_geojson(exported):
    _, _, d, cal = exported
    gj = json.loads((d / "cells.geojson").read_text())
    ids = {f["properties"]["cell_id"] for f in gj["features"]}
    assert ids == set(cal.cell_id.unique())
    f = gj["features"][0]
    ring = f["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    assert min(xs) < f["properties"]["lon_center"] < max(xs) and min(ys) < f["properties"]["lat_center"] < max(ys)
    assert isinstance(f["properties"]["is_persistent"], bool)


def test_meta(exported):
    _, _, d, _ = exported
    m = json.loads((d / "meta.json").read_text())
    for k in ("contract_version", "units", "time", "sources", "calibration", "validation", "anomalies",
              "low_confidence_rule", "caveats"):
        assert k in m, k
    assert m["time"]["first_month"] == "2000-11" and m["time"]["last_month"] == "2021-03"
    assert m["time"]["display_only_years"] == [2020, 2021]
    assert len(m["calibration"]["factors"]) == 12
    assert m["contract_version"] == "0.5" and "cells_series/2005.json" in m["files"]
