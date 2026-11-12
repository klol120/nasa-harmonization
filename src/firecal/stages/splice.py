"""Splice (method step 5): one harmonized VIIRS-equivalent series per cell and month.

Per segment (a month split at 2002-07-04 / 2012-01-20 when they fall inside it):
  before the VIIRS start: estimate = a_m * (kT_m if Terra-only) * n_modis + b_m * share_cell_m * days/month_days
  from the VIIRS start:   observed = n_viirs
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

from ..config import path
from ..fitting import chosen, ensure_fire_days, usable_dates
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
    lc = cfg["low_confidence"]
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


def factor_bands(cfg: dict, region: str) -> tuple[pd.DataFrame, str, str]:
    """Point and band factors per (month, terra_only), and the intercept b per month."""
    pick_a, pick_k = chosen(cfg, "calibration", region), chosen(cfg, "terra", region)
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


def month_flags(cfg: dict, seg: pd.DataFrame, lcm: pd.DataFrame) -> pd.DataFrame:
    """Region-wide flags per (year, month): availability, partial, estimate, gap, low confidence."""
    est = ~seg.viirs_era
    s = seg.assign(feed_days=np.where(est, seg.modis_days, seg.viirs_days),
                   gap=np.where(est, seg.gap_terra + seg.gap_aqua, seg.gap_viirs))
    s["est_seg"] = est & (s.feed_days > 0)
    m = s.groupby(["year", "month"]).agg(feed_days=("feed_days", "sum"), month_days=("month_days", "first"),
                                         is_estimate=("est_seg", "any"), gap=("gap", "sum"),
                                         modis_days=("modis_days", "sum"), viirs_days=("viirs_days", "sum")).reset_index()
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
    fb, pick_a, pick_k = factor_bands(cfg, region_name)
    lcm = low_confidence_months(cfg, region_name)
    flags = month_flags(cfg, seg, lcm)

    # sparse per-cell segment values (cells with fire-days)
    seg_info = seg[["year", "month", "seg", "ndays", "month_days", "modis_days", "viirs_days", "terra_only", "viirs_era"]]
    c = fs.groupby(["cell_id", "year", "month", "seg"])[["n_modis", "n_viirs"]].sum().reset_index()
    c = c.merge(seg_info, on=["year", "month", "seg"]).merge(fb, on=["month", "terra_only"], how="left")
    est = ~c.viirs_era
    has = np.where(est, c.modis_days, c.viirs_days) > 0
    c["val"] = np.where(has, np.where(est, c.n_modis * c.f, c.n_viirs), 0.0)
    c["lo"] = np.where(has, np.where(est, c.n_modis * c.f_low, c.n_viirs), 0.0)
    c["hi"] = np.where(has, np.where(est, c.n_modis * c.f_high, c.n_viirs), 0.0)
    parts = [c[["cell_id", "year", "month", "val", "lo", "hi"]]]
    if (fb.b != 0).any():                      # affine intercept spread over cells by VIIRS share
        sh = cell_shares(cfg, region_name)
        es = seg_info[~seg_info.viirs_era & (seg_info.modis_days > 0)].merge(fb, on=["month", "terra_only"])
        bi = sh.merge(es, on="month")
        frac = bi.ndays / bi.month_days
        parts.append(pd.DataFrame({"cell_id": bi.cell_id, "year": bi.year, "month": bi.month,
                                   "val": bi.b * bi.share * frac, "lo": bi.b_low * bi.share * frac,
                                   "hi": bi.b_high * bi.share * frac}))
    v = pd.concat(parts).groupby(["cell_id", "year", "month"])[["val", "lo", "hi"]].sum()
    raw = fs.groupby(["cell_id", "year", "month"])[["n_modis", "n_viirs"]].sum()

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
    for col in ("val", "lo", "hi", "n_modis", "n_viirs"):
        m[col] = m[col].fillna(0.0)
    m["harmonized"] = m.val.where(m.data_available).astype("float32")
    m["harmonized_low"] = m.lo.where(m.data_available).astype("float32")
    m["harmonized_high"] = m.hi.where(m.data_available).astype("float32")
    m["modis_raw"] = m.n_modis.where(m.modis_days > 0).round().astype("Int16")
    m["viirs_raw"] = m.n_viirs.where(m.viirs_days > 0).round().astype("Int16")
    m = m.merge(cells[["cell_id", "is_persistent"]].astype({"cell_id": cat}), on="cell_id")
    m["year"], m["month"] = m.year.astype("int16"), m.month.astype("int8")
    cols = ["cell_id", "year", "month", "modis_raw", "viirs_raw", "harmonized", "harmonized_low", "harmonized_high",
            "is_estimate", "has_gap", "data_available", "partial_month", "display_only", "low_confidence",
            "is_persistent"]
    m = m[cols].sort_values(key, ignore_index=True)
    report = {"strategy": pick_a, "terra_strategy": pick_k, "cells": len(cells), "rows": len(m),
              "low_confidence_months": lcm.to_dict("records"), "factor_table": fb.round(4).to_dict("records")}
    write_stage(cfg, region_name, "harmonized", m, report, ["fire_segments", "segments", "factors", "kT"])
    write_stage(cfg, region_name, "cells", cells.assign(countries=cells.countries.map(lambda x: "|".join(x))))
    log.info("splice %s: %d cells, %d rows (%s, kT %s)", region_name, len(cells), len(m), pick_a, pick_k)
    return m
