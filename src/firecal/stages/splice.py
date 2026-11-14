"""Splice (method step 5): one harmonized VIIRS-equivalent series per cell and month.

Per segment (a month split at 2002-07-04 / 2012-01-20 when they fall inside it):
  before the VIIRS start: estimate = a_m * (kT_m if Terra-only) * n_modis + b_m * share_cell_m * days/month_days
  from the VIIRS start:   observed = n_viirs (S-NPP)
  from the continuation switch (S-NPP's end): calibrated = c_m * n_noaa20, bands from the c_m bootstrap
b_m is the affine intercept (0 for ratio strategies), spread over cells by each cell's share of the
region's overlap-period VIIRS fire-days in that calendar month. Bands come from the bootstrap draws of
a_m and kT (independent draws multiplied); for affine strategies a and b quantiles are combined per
component. A segment counts as data only on days its feeding sensor has data, so a month without data
is null, never 0.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import continuation, path, region_settings
from ..fitting import chosen, composite_spec, ensure_fire_days, usable_dates
from ..geo import cell_id as make_cell_id, footprint_cells
from ..io import read_stage, write_stage

log = logging.getLogger(__name__)


def cell_table(cfg: dict, region: str, fs: pd.DataFrame) -> pd.DataFrame:
    """Cells to export: footprint cells (centre in the region's countries) plus any cell with fire-days."""
    r = cfg["regions"][region]
    size = cfg["grid"]["size_deg"]
    fp = footprint_cells(path(cfg, "boundaries"), r["countries"], r["bbox"], size)
    det_c = fs.groupby(["cell_id", "country"]).n_modis.size().rename("n").reset_index()
    ids = sorted(set(fp.cell_id) | set(fs.cell_id))
    cells = pd.DataFrame({"cell_id": ids})
    cells = cells.merge(fp, on="cell_id", how="left")
    lists = det_c.groupby("cell_id").country.agg(lambda x: sorted(set(x)))
    top = det_c.sort_values(["cell_id", "n"], ascending=[True, False]).drop_duplicates("cell_id").set_index("cell_id").country
    cells["countries"] = [sorted(set(lists.get(c, [])) | ({cc} if isinstance(cc, str) else set()))
                          for c, cc in zip(cells.cell_id, cells.centre_country)]
    cells["primary_country"] = cells.centre_country.fillna(cells.cell_id.map(top))
    rc = cells.cell_id.str.split("_", expand=True).astype(int)
    cells["row"], cells["col"] = rc[0], rc[1]
    cells["lat_center"] = np.round((cells.row + 0.5) * size - 90, 6)
    cells["lon_center"] = np.round((cells.col + 0.5) * size - 180, 6)
    stats = read_stage(cfg, region, "persistent_sources")
    flagged = stats[stats.flagged]
    pc = set(make_cell_id(flagged.lat_center.values, flagged.lon_center.values, size))
    cells["is_persistent"] = cells.cell_id.isin(pc)
    return cells.drop(columns="centre_country")


def low_confidence_months(cfg: dict, region: str) -> pd.DataFrame:
    """Calendar months whose pre-2012 estimates are low_confidence (config low_confidence rule)."""
    lc = region_settings(cfg, "low_confidence", region)
    sfx = "_np" if cfg["persistence"]["exclude_from_calibration"] else ""
    y0, y1 = cfg["calibration"]["overlap_years"]
    fd = ensure_fire_days(cfg, region)
    fd = fd[usable_dates(cfg, fd, read_stage(cfg, region, "outages"), ["Terra", "Aqua", "SNPP"])
            & fd.date.dt.year.between(y0, y1).to_numpy()]
    m = fd.date.dt.month
    v = fd[f"viirs{sfx}"]
    t = pd.DataFrame({"viirs": v.groupby(m).sum(), "zero_modis": (v & ~fd[f"modis{sfx}"]).groupby(m).sum(),
                      "modis": fd[f"modis{sfx}"].groupby(m).sum()}).reindex(range(1, 13), fill_value=0)
    t["zero_modis_share"] = (t.zero_modis / t.viirs.where(t.viirs > 0)).fillna(1.0)
    t["low_confidence"] = (t.modis < lc["min_modis_fire_days"]) | (t.zero_modis_share >= lc["max_zero_modis_share"])
    return t.rename_axis("month").reset_index()


def factor_bands(cfg: dict, region: str, pick_a: str | None = None) -> tuple[pd.DataFrame, str, str]:
    """Point and band factors per (month, terra_only), and the intercept b per month."""
    pick_a = pick_a or chosen(cfg, "calibration", region)
    pick_k = chosen(cfg, "terra", region)
    fac = read_stage(cfg, region, "factors").query("strategy == @pick_a").set_index("month")
    kt = read_stage(cfg, region, "kT").query("strategy == @pick_k").set_index("month")
    A = read_stage(cfg, region, "factors_boot").query("strategy == @pick_a").pivot(index="draw", columns="month", values="a")
    K = read_stage(cfg, region, "kT_boot").query("strategy == @pick_k").pivot(index="draw", columns="month", values="kT")
    n = min(len(A), len(K))
    A, K = A.to_numpy()[:n], K.to_numpy()[:n]
    ci = cfg["calibration"]["bootstrap"]["ci"]
    lo, hi = (1 - ci) / 2, 1 - (1 - ci) / 2
    rows = []
    for terra_only in (False, True):
        D = A * K if terra_only else A
        point = fac.a.to_numpy() * (kt.kT.to_numpy() if terra_only else 1)
        rows.append(pd.DataFrame({"month": np.arange(1, 13), "terra_only": terra_only, "f": point,
                                  "f_low": np.nanquantile(D, lo, 0), "f_high": np.nanquantile(D, hi, 0),
                                  "b": fac.b.to_numpy(), "b_low": fac.b_low.to_numpy(), "b_high": fac.b_high.to_numpy(),
                                  "kT": kt.kT.to_numpy() if terra_only else 1.0}))
    return pd.concat(rows, ignore_index=True), pick_a, pick_k


def cell_shares(cfg: dict, region: str) -> pd.DataFrame:
    """Each cell's share of region VIIRS fire-days per calendar month on the overlap (for b)."""
    sfx = "_np" if cfg["persistence"]["exclude_from_calibration"] else ""
    y0, y1 = cfg["calibration"]["overlap_years"]
    fs = read_stage(cfg, region, "fire_segments")
    o = fs[fs.year.between(y0, y1)].groupby(["cell_id", "month"])[f"n_viirs{sfx}"].sum().rename("v").reset_index()
    o["share"] = o.v / o.groupby("month").v.transform("sum")
    return o[["cell_id", "month", "share"]]


def estimate_rows(cfg: dict, region: str, fs: pd.DataFrame, seg_info: pd.DataFrame, fb: pd.DataFrame) -> pd.DataFrame:
    """Estimated (pre-VIIRS) segment values per cell: a_m (x kT) x n_modis plus the spread intercept."""
    c = fs.groupby(["cell_id", "year", "month", "seg"])[["n_modis"]].sum().reset_index()
    c = c.merge(seg_info, on=["year", "month", "seg"])
    c = c[~c.viirs_era & (c.modis_days > 0)].merge(fb, on=["month", "terra_only"], how="left")
    parts = [pd.DataFrame({"cell_id": c.cell_id, "year": c.year, "month": c.month, "terra_only": c.terra_only,
                           "val": c.n_modis * c.f, "lo": c.n_modis * c.f_low, "hi": c.n_modis * c.f_high})]
    if (fb.b != 0).any():                      # affine intercept spread over cells by VIIRS share
        sh = cell_shares(cfg, region)
        es = seg_info[~seg_info.viirs_era & (seg_info.modis_days > 0)].merge(fb, on=["month", "terra_only"])
        bi = sh.merge(es, on="month")
        frac = bi.ndays / bi.month_days
        parts.append(pd.DataFrame({"cell_id": bi.cell_id, "year": bi.year, "month": bi.month,
                                   "terra_only": bi.terra_only, "val": bi.b * bi.share * frac,
                                   "lo": bi.b_low * bi.share * frac, "hi": bi.b_high * bi.share * frac}))
    return pd.concat(parts, ignore_index=True)


def observed_rows(fs: pd.DataFrame, seg_info: pd.DataFrame) -> pd.DataFrame:
    c = fs.groupby(["cell_id", "year", "month", "seg"])[["n_viirs"]].sum().reset_index()
    c = c.merge(seg_info, on=["year", "month", "seg"])
    c = c[c.viirs_era & ~c.cont_era & (c.viirs_days > 0)]
    return pd.DataFrame({"cell_id": c.cell_id, "year": c.year, "month": c.month,
                         "val": c.n_viirs.astype(float), "lo": c.n_viirs.astype(float), "hi": c.n_viirs.astype(float)})


def continuation_factors(cfg: dict, region: str) -> tuple[pd.DataFrame, str]:
    """c_m with its bootstrap band for the region's continuation strategy."""
    pick = chosen(cfg, "continuation", region)
    f = read_stage(cfg, region, "cont_factors").query("strategy == @pick")
    return f[["month", "a", "a_low", "a_high"]].rename(columns={"a": "c", "a_low": "c_low", "a_high": "c_high"}), pick


def continuation_rows(fs: pd.DataFrame, seg_info: pd.DataFrame, cf: pd.DataFrame) -> pd.DataFrame:
    """Segments from the switch: NOAA-20 fire-days converted to S-NPP units."""
    c = fs.groupby(["cell_id", "year", "month", "seg"])[["n_noaa20"]].sum().reset_index()
    c = c.merge(seg_info, on=["year", "month", "seg"])
    c = c[c.cont_era & (c.noaa20_days > 0)].merge(cf, on="month", how="left")
    return pd.DataFrame({"cell_id": c.cell_id, "year": c.year, "month": c.month,
                         "val": c.n_noaa20 * c.c, "lo": c.n_noaa20 * c.c_low, "hi": c.n_noaa20 * c.c_high})


def shape_level_rows(shape: pd.DataFrame, level: pd.DataFrame, fb_level: pd.DataFrame) -> pd.DataFrame:
    """Composite: shape rows rescaled per year so the region's yearly estimated total equals the level
    model's. Bands carry the level model's factor uncertainty (f_low/f, f_high/f per month); the
    shape model's own uncertainty is not propagated. Years whose shape total is 0 keep the level rows."""
    ts = shape.groupby("year").val.sum()
    tl = level.groupby("year").val.sum()
    scale = (tl / ts.where(ts > 0)).rename("scale")
    out = shape.merge(scale, left_on="year", right_index=True, how="left")
    keep_level = out.scale.isna()
    out = out[~keep_level]
    out["val"] = out.val * out.scale
    r = fb_level.assign(r_lo=fb_level.f_low / fb_level.f, r_hi=fb_level.f_high / fb_level.f)[
        ["month", "terra_only", "r_lo", "r_hi"]]
    out = out.merge(r, on=["month", "terra_only"], how="left")
    out["lo"], out["hi"] = out.val * out.r_lo, out.val * out.r_hi
    fallback = level[level.year.isin(scale.index[scale.isna()])]
    return pd.concat([out[["cell_id", "year", "month", "terra_only", "val", "lo", "hi"]], fallback], ignore_index=True)


def month_flags(cfg: dict, seg: pd.DataFrame, lcm: pd.DataFrame) -> pd.DataFrame:
    """Region-wide flags per (year, month): availability, partial, estimate, gap, low confidence."""
    est, cont = ~seg.viirs_era, seg.cont_era.astype(bool)
    s = seg.assign(feed_days=np.select([est, cont], [seg.modis_days, seg.noaa20_days], seg.viirs_days),
                   gap=np.select([est, cont], [seg.gap_terra + seg.gap_aqua, seg.gap_noaa20], seg.gap_viirs))
    s["est_seg"] = est & (s.feed_days > 0)
    # source feeding each segment; a month's source joins its segments' sources ("MODIS+SNPP" for 2012-01)
    s["seg_source"] = np.where(s.feed_days > 0, np.select([est, cont], ["MODIS", "NOAA20"], "SNPP"), "")
    m = s.groupby(["year", "month"]).agg(feed_days=("feed_days", "sum"), month_days=("month_days", "first"),
                                         is_estimate=("est_seg", "any"), gap=("gap", "sum"),
                                         modis_days=("modis_days", "sum"), viirs_days=("viirs_days", "sum"),
                                         noaa20_days=("noaa20_days", "sum"),
                                         source=("seg_source", lambda x: "+".join(dict.fromkeys(v for v in x if v)))
                                         ).reset_index()
    m["source"] = m.source.replace("", None)
    m["data_available"] = m.feed_days > 0
    m["partial_month"] = m.data_available & (m.feed_days < m.month_days)
    m["has_gap"] = m.gap > 0
    m["display_only"] = m.year > cfg["years"]["stats_last_year"]
    m = m.merge(lcm[["month", "low_confidence"]].rename(columns={"low_confidence": "lc_month"}), on="month")
    m["low_confidence"] = m.is_estimate & m.lc_month
    return m


def run(cfg: dict, region_name: str) -> pd.DataFrame:
    fs = read_stage(cfg, region_name, "fire_segments")
    seg = read_stage(cfg, region_name, "segments")
    cells = cell_table(cfg, region_name, fs)
    pick = chosen(cfg, "calibration", region_name)
    comp = composite_spec(cfg, pick)
    lcm = low_confidence_months(cfg, region_name)
    flags = month_flags(cfg, seg, lcm)
    seg_info = seg[["year", "month", "seg", "ndays", "month_days", "modis_days", "viirs_days", "noaa20_days",
                    "terra_only", "viirs_era", "cont_era"]]
    if comp:
        fbS, _, pick_k = factor_bands(cfg, region_name, comp["shape"])
        fbL, _, _ = factor_bands(cfg, region_name, comp["level"])
        est = shape_level_rows(estimate_rows(cfg, region_name, fs, seg_info, fbS),
                               estimate_rows(cfg, region_name, fs, seg_info, fbL), fbL)
        fb = pd.concat([fbS.assign(component="shape", strategy=comp["shape"]),
                        fbL.assign(component="level", strategy=comp["level"])])
    else:
        fb, _, pick_k = factor_bands(cfg, region_name, pick)
        est = estimate_rows(cfg, region_name, fs, seg_info, fb)
    pick_a = pick
    parts = [est[["cell_id", "year", "month", "val", "lo", "hi"]], observed_rows(fs, seg_info)]
    cont, pick_c = continuation(cfg), None
    if cont:
        cf, pick_c = continuation_factors(cfg, region_name)
        parts.append(continuation_rows(fs, seg_info, cf))
    v = pd.concat(parts).groupby(["cell_id", "year", "month"])[["val", "lo", "hi"]].sum()
    raw = fs.groupby(["cell_id", "year", "month"])[["n_modis", "n_viirs", "n_noaa20"]].sum()

    # dense grid: every cell x every month
    cat = pd.CategoricalDtype(cells.cell_id.sort_values())
    ym = flags[["year", "month"]]
    grid = pd.DataFrame({"cell_id": pd.Categorical(np.repeat(cat.categories, len(ym)), dtype=cat),
                         "year": np.tile(ym.year.to_numpy(), len(cat.categories)),
                         "month": np.tile(ym.month.to_numpy(), len(cat.categories))})
    key = ["cell_id", "year", "month"]
    vv = v.reset_index().astype({"cell_id": cat})
    rr = raw.reset_index().astype({"cell_id": cat})
    m = grid.merge(vv, on=key, how="left").merge(rr, on=key, how="left").merge(flags, on=["year", "month"], how="left")
    for col in ("val", "lo", "hi", "n_modis", "n_viirs", "n_noaa20"):
        m[col] = m[col].fillna(0.0)
    m["harmonized"] = m.val.where(m.data_available).astype("float32")
    m["harmonized_low"] = m.lo.where(m.data_available).astype("float32")
    m["harmonized_high"] = m.hi.where(m.data_available).astype("float32")
    m["modis_raw"] = m.n_modis.where(m.modis_days > 0).round().astype("Int16")
    m["viirs_raw"] = m.n_viirs.where(m.viirs_days > 0).round().astype("Int16")
    m["noaa20_raw"] = m.n_noaa20.where(m.noaa20_days > 0).round().astype("Int16")
    m = m.merge(cells[["cell_id", "is_persistent"]].astype({"cell_id": cat}), on="cell_id")
    m["year"], m["month"] = m.year.astype("int16"), m.month.astype("int8")
    cols = ["cell_id", "year", "month", "modis_raw", "viirs_raw", "noaa20_raw", "harmonized", "harmonized_low",
            "harmonized_high", "source", "is_estimate", "has_gap", "data_available", "partial_month", "display_only", "low_confidence",
            "is_persistent"]
    m = m[cols].sort_values(key, ignore_index=True)
    report = {"strategy": pick_a, "terra_strategy": pick_k, "continuation_strategy": pick_c, "cells": len(cells), "rows": len(m),
              "low_confidence_months": lcm.to_dict("records"), "factor_table": fb.round(4).to_dict("records")}
    write_stage(cfg, region_name, "harmonized", m, report, ["fire_segments", "segments", "factors", "kT"])
    write_stage(cfg, region_name, "cells", cells.assign(countries=cells.countries.map(lambda x: "|".join(x))))
    log.info("splice %s: %d cells, %d rows (%s, kT %s)", region_name, len(cells), len(m), pick_a, pick_k)
    return m
