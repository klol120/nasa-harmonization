"""NOAA-20 continuation after S-NPP's end (synthetic region with a known S-NPP / NOAA-20 ratio)."""
import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from firecal.config import load_config
from firecal.io import read_report, read_stage
from firecal.stages import (anomalies, calibrate, clean, continuation, export, grid, ingest, splice, terra,
                            validate)
from synthetic import SynthSpec, config_overrides, write_csvs

SWITCH = dt.date(2016, 6, 15)      # mid-month: June 2016 is split S-NPP / NOAA-20


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cont")
    spec = SynthSpec(seed=31, start=dt.date(2001, 1, 1), end=dt.date(2016, 9, 30), n_rows=12, n_cols=12,
                     noaa20_start=dt.date(2013, 1, 1), snpp_end=SWITCH - dt.timedelta(days=1))
    w = write_csvs(spec, tmp / "raw")
    ov = config_overrides(spec, tmp)
    ov["calibration"] = {"overlap_years": [2012, 2015], "holdout": {"fit": [2012, 2013], "test": [2014, 2015]},
                         "strategies": ["single", "local"], "strategy": "local", "bootstrap": {"n": 300}}
    ov["terra"] = {"fit_years": [2003, 2010], "strategies": ["single", "local"], "strategy": "local"}
    ov["continuation"] = {"overlap_years": [2013, 2015], "holdout": {"fit": [2013, 2014], "test": [2015, 2015]},
                          "strategies": ["single", "local"], "strategy": "local"}
    ov["years"] = {"stats_last_year": 2015, "display_last_month": "2016-12"}
    ov["anomalies"] = {"baseline_years": [2001, 2015], "sensitivity_baselines": [], "min_sd": 0, "by_region!": {}}
    cfg = load_config(overrides=ov)
    for stage in (ingest, clean, grid, terra, calibrate, continuation, validate, splice, anomalies, export):
        stage.run(cfg, "synth")
    d = tmp / "export" / "synth"
    return cfg, spec, w, d


def test_snpp_flag_is_snpp_only(run):
    cfg, spec, w, _ = run
    fd = read_stage(cfg, "synth", "fire_days")
    v = w["viirs"]
    v = v[~v._noise]
    cells = (np.floor((v.latitude + 90) / 0.05 + 1e-9).astype(int).astype(str) + "_" +
             np.floor((v.longitude + 180) / 0.05 + 1e-9).astype(int).astype(str))
    for sat, col in (("N", "viirs"), ("N20", "noaa20")):
        m = (v.satellite == sat).to_numpy()
        assert fd[col].sum() == len(set(zip(cells[m], v.acq_date[m])))


def test_factors_recover_truth(run):
    cfg, spec, _, _ = run
    f = read_stage(cfg, "synth", "cont_factors")
    truth = spec.truth()["c"]
    loc = f[f.strategy == "local"].set_index("month")
    assert np.allclose(loc.a, truth, rtol=0.12)
    covered = ((loc.a_low <= truth) & (truth <= loc.a_high)).sum()
    assert covered >= 9                                   # 90% bands, 12 months
    single = f[f.strategy == "single"].a.iloc[0]
    assert loc.a.min() * 0.95 < single < loc.a.max() * 1.05


def test_continuity_at_switch(run):
    cfg, _, _, _ = run
    c = read_report(cfg, "synth", "cont_factors")["continuity"]
    assert c["window"] == ["2016-01-01", "2016-06-14"]
    assert c["band"][0] <= 1 <= c["band"][1] and not c["step_flagged"]
    assert c["step_index"] == pytest.approx(1, abs=0.06)


def test_splice_after_switch_uses_calibrated_noaa20(run):
    cfg, _, _, _ = run
    c = read_stage(cfg, "synth", "cont_factors").query("strategy == 'local'").set_index("month")
    fs = read_stage(cfg, "synth", "fire_segments")
    h = read_stage(cfg, "synth", "harmonized")
    aug = h[(h.year == 2016) & (h.month == 8)]
    n = fs[(fs.year == 2016) & (fs.month == 8)].n_noaa20.sum()
    assert aug.harmonized.sum() == pytest.approx(c.a[8] * n, rel=1e-5)
    assert aug.harmonized_low.sum() == pytest.approx(c.a_low[8] * n, rel=1e-5)
    assert aug.viirs_raw.isna().all() and aug.noaa20_raw.sum() == n
    jun = fs[(fs.year == 2016) & (fs.month == 6)]
    expected = jun[jun.seg == 0].n_viirs.sum() + c.a[6] * jun[jun.seg == 1].n_noaa20.sum()
    assert h[(h.year == 2016) & (h.month == 6)].harmonized.sum() == pytest.approx(expected, rel=1e-5)


def test_source_field(run):
    _, _, _, d = run
    r = pd.read_csv(d / "region_monthly.csv", keep_default_na=False, na_values=[""]).set_index("ym")
    assert (r.loc["2001-01":"2011-12", "source"] == "MODIS").all()
    assert r.loc["2012-01", "source"] == "MODIS+SNPP"
    assert (r.loc["2012-02":"2016-05", "source"] == "SNPP").all()
    assert r.loc["2016-06", "source"] == "SNPP+NOAA20"
    assert (r.loc["2016-07":"2016-09", "source"] == "NOAA20").all()
    assert r.loc["2016-10":"2016-12", "source"].isna().all() and not r.loc["2016-10":, "data_available"].any()
    obs = r[r.source == "SNPP"]
    assert np.allclose(obs.harmonized, obs.viirs_raw, rtol=1e-4)
    assert not r[r.source.fillna("").str.contains("NOAA20")].is_estimate.any()
    j = json.loads((d / "region_monthly.json").read_text())
    assert {x["source"] for x in j} == {"MODIS", "MODIS+SNPP", "SNPP", "SNPP+NOAA20", "NOAA20", None}


def test_meta_continuation(run):
    _, _, _, d = run
    m = json.loads((d / "meta.json").read_text())
    c = m["calibration"]["continuation"]
    assert c["satellite"] == "NOAA20" and c["switch_date"] == "2016-06-15" and len(c["factors"]) == 12
    assert m["time"]["viirs_switch_date"] == "2016-06-15"
    assert {"VIIRS_SNPP_SP", "VIIRS_NOAA20_SP"} <= set(m["sources"])


def test_without_continuation_nothing_changes(synth):
    cfg, _, _ = synth
    assert continuation.run(cfg, "synth") is None
