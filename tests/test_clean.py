import datetime as dt

import numpy as np
import pandas as pd
import pytest

from firecal.config import load_config
from firecal.firedays import count_by_sensor
from firecal.io import read_report, read_stage
from firecal.stages import clean, ingest
from synthetic import SynthSpec, config_overrides, write_csvs


def run_both(cfg, region="synth"):
    ingest.run(cfg, region)
    return clean.run(cfg, region), read_report(cfg, region, "detections_clean")


def test_ingest_reads_all_rows(synth):
    cfg, spec, w = synth
    df = ingest.run(cfg, "synth")
    assert len(df) == len(w["modis"]) + len(w["viirs"])
    assert set(df.country) == {spec.country}


def test_clean_removes_exactly_the_noise(synth):
    cfg, spec, w = synth
    df, rep = run_both(cfg)
    noise = pd.concat([w["modis"], w["viirs"]])
    n_static = int((noise._noise & (noise.type == 2)).sum())
    assert rep["removed"]["fire_type"] == n_static
    assert rep["removed"]["confidence"] == int((noise._noise & (noise.type == 0)).sum())
    assert rep["removed"]["duplicates"] == 0
    assert len(df) == int((~noise._noise).sum())


def test_duplicate_file_is_removed(synth, tmp_path):
    cfg, spec, w = synth
    f = next(p for p in w["files"] if p.name == "VIIRS_SNPP_SP_2013.csv")
    f.with_name("VIIRS_SNPP_SP_9999.csv").write_text(f.read_text())   # same rows again
    _, rep = run_both(cfg)
    assert rep["removed"]["duplicates"] == len(pd.read_csv(f)) - int((pd.read_csv(f).type != 0).sum() +
                                                                     (pd.read_csv(f).confidence == "l").sum())


def _nrt_copy(w, tmp_path, start, end):
    v = w["viirs"]
    # keep `country`: without it ingest tags the synthetic points by Natural Earth (Chad) and drops them
    v = v[(~v._noise) & (v.acq_date >= start) & (v.acq_date <= end)].drop(columns=["type", "_noise"])
    v = v.assign(version="2.0NRT", latitude=v.latitude + 1e-5)   # NRT positions differ slightly from SP
    f = tmp_path / "nrt.csv"
    v.to_csv(f, index=False)
    return f, len(v)


def test_sp_preferred_over_nrt(tmp_path):
    spec = SynthSpec(seed=2, start=dt.date(2012, 1, 1), end=dt.date(2013, 12, 31))
    w = write_csvs(spec, tmp_path / "raw")
    f, n = _nrt_copy(w, tmp_path, "2013-06-01", "2013-12-31")
    ov = config_overrides(spec, tmp_path)
    ov["inputs"].append({"path": str(f), "format": "firms_nrt_csv", "source": "auto"})
    ov["coverage!"]["VIIRS_SNPP_SP"] = [spec.viirs_start, dt.date(2013, 8, 31)]   # SP ends 08-31 here
    ov["coverage!"]["VIIRS_SNPP_NRT"] = [dt.date(2013, 6, 1), spec.end]
    cfg = load_config(overrides=ov)
    df, rep = run_both(cfg)
    nrt = df[df.source == "VIIRS_SNPP_NRT"]
    assert rep["removed"]["nrt_where_sp_exists"] > 0
    assert nrt.datetime_utc.min() >= pd.Timestamp("2013-09-01", tz="UTC")


@pytest.mark.parametrize("mode", ["auto", "always", "off"])
def test_persistent_modes(tmp_path, mode):
    spec = SynthSpec(seed=3, start=dt.date(2012, 1, 1), end=dt.date(2016, 12, 31))
    w = write_csvs(spec, tmp_path / "raw")
    # A persistent night source: every 10th night for 5 years, in one fine cell that the synthetic fires never
    # reach (they stay within ±0.015° of 0.05° cell centres), once typed (SP) and once untyped (NRT).
    days = pd.date_range("2012-01-25", "2016-12-31", freq="10D")
    lat, lon = 10.1495, 20.1495
    src = pd.DataFrame({"latitude": lat, "longitude": lon, "bright_ti4": 300, "scan": .4, "track": .4,
                        "acq_date": days.strftime("%Y-%m-%d"), "acq_time": "0010", "satellite": "N",
                        "instrument": "VIIRS", "confidence": "n", "version": "2", "bright_ti5": 290, "frp": 1.0,
                        "daynight": "N"})
    typed = tmp_path / "typed.csv"
    src.assign(type=0, country=spec.country).to_csv(typed, index=False)
    untyped = tmp_path / "untyped.csv"
    src.assign(acq_time="0020", version="2.0NRT", country=spec.country).to_csv(untyped, index=False)
    ov = config_overrides(spec, tmp_path)
    ov["inputs"] += [{"path": str(typed), "format": "firms_archive_csv", "source": "VIIRS_SNPP_SP"},
                     {"path": str(untyped), "format": "firms_nrt_csv", "source": "auto"}]
    ov["coverage!"]["VIIRS_SNPP_NRT"] = [spec.viirs_start, spec.end]
    # keep the NRT rows: SP "covers" a single day only, so SP precedence does not apply here
    ov["coverage!"]["VIIRS_SNPP_SP"] = [spec.viirs_start, spec.viirs_start]
    ov["persistence"] = {"mode": mode, "cell_deg": 0.01, "min_year_frac": 0.8, "min_night_frac": 0.9,
                                 "diagnostic_regions": []}
    cfg = load_config(overrides=ov)
    df, rep = run_both(cfg)
    in_src = (df.lat == lat) & (df.lon == lon)
    stats = read_stage(cfg, "synth", "persistent_sources")
    assert stats.flagged.sum() >= 1
    expected = {"auto": len(days), "always": 0, "off": 2 * len(days)}[mode]
    assert in_src.sum() == expected


def test_outages_known_and_suspect(tmp_path):
    spec = SynthSpec(seed=4, start=dt.date(2012, 1, 1), end=dt.date(2014, 12, 31), n_rows=20, n_cols=20)
    w = write_csvs(spec, tmp_path / "raw")
    f = next(p for p in w["files"] if p.name == "VIIRS_SNPP_SP_2013.csv")
    v = pd.read_csv(f, dtype=str)
    v[~v.acq_date.between("2013-08-10", "2013-08-14")].to_csv(f, index=False)    # 5-day summer outage
    ov = config_overrides(spec, tmp_path)
    ov["gaps"]["known"] = [{"satellite": "Terra", "start": dt.date(2013, 2, 1), "end": dt.date(2013, 2, 3)}]
    cfg = load_config(overrides=ov)
    run_both(cfg)
    o = read_stage(cfg, "synth", "outages")
    sus = set(o[(o.kind == "suspect") & (o.satellite == "SNPP")].date.dt.strftime("%Y-%m-%d"))
    planted = {f"2013-08-{d}" for d in range(10, 15)}
    assert planted <= sus
    assert len(sus - planted) <= 3   # rare natural zero days in winter are allowed
    k = o[o.kind == "known"]
    assert len(k) == 3 and k.flagged.all()
    assert not o[o.kind == "suspect"].flagged.any()


def test_fire_days_collapse_clusters_and_match_truth(tmp_path):
    spec = SynthSpec(seed=5, start=dt.date(2012, 1, 20), end=dt.date(2020, 12, 31), n_rows=12, n_cols=12)
    w = write_csvs(spec, tmp_path / "raw")
    cfg = load_config(overrides=config_overrides(spec, tmp_path))
    df, _ = run_both(cfg)
    n = count_by_sensor(df, 0.05)
    days = pd.date_range(spec.start, spec.end)
    q = spec.q[days.month - 1]
    pm = (1 - (1 - spec.p_terra) * (1 - spec.p_aqua))[days.month - 1]
    expected = (q * spec.p_viirs[days.month - 1]).sum() / (q * pm).sum()
    assert n["VIIRS"] / n["MODIS"] == pytest.approx(expected, rel=0.03)
    det_ratio = (df.sensor == "VIIRS").sum() / (df.sensor == "MODIS").sum()
    assert det_ratio > 1.5 * expected   # raw detections over-count VIIRS clusters


def test_untyped_rows_dropped_in_static_cells(tmp_path):
    """NRT rows have no `type`: in fine cells the SP record marks as static (type 2) they are dropped too."""
    spec = SynthSpec(seed=6, start=dt.date(2012, 1, 1), end=dt.date(2013, 12, 31))
    write_csvs(spec, tmp_path / "raw")
    days = pd.date_range("2012-02-01", "2013-12-31", freq="7D")
    lat, lon = 10.1495, 20.1495          # a fine cell the synthetic fires never reach
    src = pd.DataFrame({"latitude": lat, "longitude": lon, "bright_ti4": 300, "scan": .4, "track": .4,
                        "acq_date": days.strftime("%Y-%m-%d"), "acq_time": "1300", "satellite": "N",
                        "instrument": "VIIRS", "confidence": "n", "version": "2", "bright_ti5": 290, "frp": 5.0,
                        "daynight": "D", "country": spec.country})
    typed, untyped = tmp_path / "typed.csv", tmp_path / "untyped.csv"
    src.assign(type=2).to_csv(typed, index=False)
    src.assign(acq_time="1310", version="2.0NRT").to_csv(untyped, index=False)
    ov = config_overrides(spec, tmp_path)
    ov["inputs"] += [{"path": str(typed), "format": "firms_archive_csv", "source": "VIIRS_SNPP_SP"},
                     {"path": str(untyped), "format": "firms_nrt_csv", "source": "auto"}]
    ov["coverage!"]["VIIRS_SNPP_NRT"] = [spec.viirs_start, spec.end]
    ov["coverage!"]["VIIRS_SNPP_SP"] = [spec.viirs_start, spec.viirs_start]   # keep the NRT rows
    df, rep = run_both(load_config(overrides=ov))
    assert rep["removed"]["untyped_in_static_cells"] == len(days)
    assert not ((df.lat == lat) & (df.lon == lon)).any()
