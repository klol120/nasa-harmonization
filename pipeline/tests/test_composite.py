"""Composite strategy (monthly shape from one model, annual level from another) through the pipeline."""
import datetime as dt

import numpy as np
import pytest

from firecal.config import load_config
from firecal.io import read_report, read_stage
from firecal.stages import anomalies, calibrate, clean, grid, ingest, splice, terra, validate
from synthetic import SynthSpec, config_overrides, write_csvs


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("composite")
    spec = SynthSpec(seed=31, start=dt.date(2000, 11, 1), end=dt.date(2020, 12, 31), n_rows=10, n_cols=10)
    write_csvs(spec, tmp / "raw")
    ov = config_overrides(spec, tmp)
    ov["calibration"] = {"strategies": ["single", "local"], "strategy": "shape_single",
                         "composites!": {"shape_single": {"shape": "affine_local", "level": "single"}},
                         "bootstrap": {"n": 100}}
    ov["terra"] = {"strategies": ["single", "local"], "strategy": "single"}
    cfg = load_config(overrides=ov)
    for stage in (ingest, clean, grid, terra, calibrate, validate, splice, anomalies):
        stage.run(cfg, "synth")
    return cfg


def test_estimated_year_totals_match_level_model(run):
    cfg = run
    h = read_stage(cfg, "synth", "harmonized")
    fac = read_stage(cfg, "synth", "factors").set_index(["strategy", "month"])
    kT = read_stage(cfg, "synth", "kT").query("strategy == 'single'").kT.iloc[0]
    a_single = fac.loc["single"].a.iloc[0]
    fs = read_stage(cfg, "synth", "fire_segments")
    seg = read_stage(cfg, "synth", "segments")
    x = fs.groupby(["year", "month", "seg"]).n_modis.sum().reset_index().merge(seg, on=["year", "month", "seg"])
    x = x[~x.viirs_era & (x.year <= 2011)]
    level = (x.n_modis * a_single * np.where(x.terra_only, kT, 1.0)).groupby(x.year).sum()
    got = h[h.year <= 2011].groupby("year").harmonized.sum()
    assert np.allclose(got.reindex(level.index), level, rtol=1e-4)


def test_monthly_shape_follows_shape_model(run):
    cfg = run
    h = read_stage(cfg, "synth", "harmonized")
    fac = read_stage(cfg, "synth", "factors").query("strategy == 'affine_local'").set_index("month")
    fs = read_stage(cfg, "synth", "fire_segments")
    y = 2008
    m = fs[fs.year == y].groupby("month").n_modis.sum().reindex(range(1, 13), fill_value=0)
    shape = fac.a * m + fac.b
    got = h[h.year == y].groupby("month").harmonized.sum()
    assert np.allclose(got / got.sum(), shape / shape.sum(), atol=1e-4)


def test_composite_in_holdout_and_continuity(run):
    cfg = run
    ho = read_stage(cfg, "synth", "holdout")
    assert {"shape_single", "single", "local"} <= set(ho.strategy)
    single = ho[ho.strategy == "single"].set_index(["variant", "fold"]).bias
    comp = ho[ho.strategy == "shape_single"].set_index(["variant", "fold"]).bias
    assert np.allclose(comp, single.reindex(comp.index), atol=1e-6)    # annual totals = single's
    cont = read_report(cfg, "synth", "holdout")["continuity"]["pdf_rules"]
    assert cont["strategy"] == "shape_single" and np.isfinite(cont["step_index"])
