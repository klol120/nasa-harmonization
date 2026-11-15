"""Grid stage details and the full ingest -> validate chain on synthetic data with a known truth."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from firecal.config import load_config
from firecal.io import read_report, read_stage
from firecal.stages import calibrate, clean, grid, ingest, terra, validate
from firecal.stages.grid import build_fire_days, segment_of
from synthetic import SynthSpec, config_overrides, write_csvs


def test_segments_split_at_boundaries():
    dates = pd.Series(pd.to_datetime(["2002-07-03", "2002-07-04", "2002-08-01", "2012-01-19", "2012-01-20"]))
    seg = segment_of(dates, [dt.date(2002, 7, 4), dt.date(2012, 1, 20)])
    assert seg.tolist() == [0, 1, 0, 0, 1]


def test_fire_days_flags_and_country_mode():
    t = pd.Timestamp("2015-08-01 11:00", tz="UTC")
    det = pd.DataFrame({
        "lat": [33.51, 33.52, 33.53, 33.51, 33.51], "lon": [35.01, 35.02, 35.03, 35.01, 35.01],
        "datetime_utc": [t, t, t, t, t + pd.Timedelta(days=1)],
        "satellite": pd.Categorical(["SNPP", "SNPP", "SNPP", "Aqua", "Terra"]),
        "country": ["Lebanon", "Syria", "Lebanon", "Lebanon", "Lebanon"]})
    persistent = np.array([True, False, False, False, False])
    fd = build_fire_days(det, persistent, 0.05).sort_values("date")
    assert len(fd) == 2                                   # 3 VIIRS pixels + Aqua collapse to one cell-day
    d1 = fd.iloc[0]
    assert d1.viirs and d1.aqua and d1.modis and not d1.terra and d1.country == "Lebanon"
    assert d1.viirs_np and d1.persistent                  # a non-persistent VIIRS pixel remains
    assert fd.iloc[1].terra and not fd.iloc[1].viirs


@pytest.fixture(scope="module")
def synth_full(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("full")
    spec = SynthSpec(seed=11, start=dt.date(2000, 11, 1), end=dt.date(2020, 12, 31), n_rows=20, n_cols=20,
                     noise_static_per_year=10)
    write_csvs(spec, tmp / "raw")
    ov = config_overrides(spec, tmp)
    ov["calibration"] = {"strategies": ["single", "local"], "strategy": "local", "bootstrap": {"n": 200}}
    ov["terra"] = {"strategies": ["single", "local"], "strategy": "local"}
    cfg = load_config(overrides=ov)
    for stage in (ingest, clean, grid, terra, calibrate, validate):
        stage.run(cfg, "synth")
    return cfg, spec


def test_calibration_recovers_true_a(synth_full):
    cfg, spec = synth_full
    f = read_stage(cfg, "synth", "factors")
    a = f[f.strategy == "local"].sort_values("month")
    truth = spec.truth()["a"]
    assert np.allclose(a.a, truth, rtol=0.12), (a.a.round(3).tolist(), truth.round(3).tolist())
    covered = ((a.a_low <= truth) & (truth <= a.a_high)).mean()
    assert covered >= 0.6


def test_terra_correction_recovers_true_kT(synth_full):
    cfg, spec = synth_full
    k = read_stage(cfg, "synth", "kT")
    k = k[k.strategy == "local"].sort_values("month")
    assert np.allclose(k.kT, spec.truth()["kT"], rtol=0.08)


def test_validation_on_synthetic(synth_full):
    cfg, _ = synth_full
    h = read_stage(cfg, "synth", "holdout")
    fwd = h[(h.fold == "forward") & (h.variant == "pdf_rules")].set_index("strategy")
    assert abs(fwd.loc["local", "bias"]) < 0.05
    rep = read_report(cfg, "synth", "holdout")
    cont = rep["continuity"]["pdf_rules"]
    assert not cont["step_flagged"] and abs(cont["step_index"] - 1) < 0.1
