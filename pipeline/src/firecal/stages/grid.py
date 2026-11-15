"""Grid: detections -> fire-days per 0.05° cell (method step 1), plus the segment calendar.

Outputs per region:
  fire_days      one row per (cell_id, date) with at least one detection; boolean flags per satellite,
                 the same flags without persistent-source detections (*_np), and the fire-day's country
                 (most common among its detections) for donor subsetting.
  fire_segments  fire-day counts per (cell_id, country, year, month, seg) for splice/export.
  segments       region-wide calendar: each month split at the config boundaries that fall inside it
                 (Terra-only cutoff, VIIRS start, VIIRS continuation switch), with days, sensor
                 availability and outage days.

`viirs` is S-NPP only; NOAA-20 has its own flag (`noaa20`) and is used only after the switch.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from ..config import as_date, continuation
from ..geo import cell_id, cell_index
from ..io import read_stage, write_stage
from ..outages import satellite_coverage

log = logging.getLogger(__name__)
SATS = {"Terra": "terra", "Aqua": "aqua", "SNPP": "viirs", "NOAA20": "noaa20"}
FLAGS = ["terra", "aqua", "modis", "viirs", "noaa20"]
DAY_COLS = ["terra", "aqua", "modis", "viirs", "noaa20"]
GAP_COLS = ["terra", "aqua", "viirs", "noaa20"]


def boundaries(cfg: dict) -> list[dt.date]:
    b = {as_date(cfg["sensors"]["terra_only_until"]), as_date(cfg["sensors"]["viirs_start"])}
    if (c := continuation(cfg)):
        b.add(c["switch_date"])
    return sorted(b)


def segment_of(dates: pd.Series, bounds: list[dt.date]) -> np.ndarray:
    """0 for the part of a month before an in-month boundary, 1 after it."""
    seg = np.zeros(len(dates), dtype=np.int8)
    for b in bounds:
        if b.day == 1:
            continue
        b = pd.Timestamp(b)
        seg += ((dates.dt.year == b.year) & (dates.dt.month == b.month) & (dates >= b)).to_numpy(np.int8)
    return seg


def persistent_mask(cfg: dict, region_name: str, det: pd.DataFrame) -> np.ndarray:
    p = cfg["persistence"]
    stats = read_stage(cfg, region_name, "persistent_sources")
    flagged = set(stats.pcell[stats.flagged])
    row, col = cell_index(det.lat, det.lon, p["cell_deg"])
    pcell = pd.Series(row).astype(str).values + "_" + pd.Series(col).astype(str).values
    return np.isin(pcell, list(flagged))


def build_fire_days(det: pd.DataFrame, persistent: np.ndarray, size: float) -> pd.DataFrame:
    d = pd.DataFrame({"cell_id": cell_id(det.lat.values, det.lon.values, size).values,
                      "date": det.datetime_utc.dt.tz_convert(None).dt.normalize().values,
                      "country": det.country.astype(str).values})
    sat = det.satellite.astype(str).values
    for s, col in SATS.items():
        d[col] = sat == s
        d[f"{col}_np"] = d[col] & ~persistent
    d["persistent"] = persistent
    keys = ["cell_id", "date"]
    agg = d.groupby(keys)[[c for c in d.columns if c not in (*keys, "country")]].max()
    # country vote by the original constellation's detections; NOAA-20 votes only on cell-days it alone
    # observed, so adding it leaves the donor subsets of the S-NPP era unchanged
    d["primary"] = ~d.noaa20
    cc = d.groupby([*keys, "country"]).agg(n=("primary", "sum"), n_all=("primary", "size")).reset_index()
    cc["n"] = cc.n.where(cc.groupby(keys).n.transform("max") > 0, cc.n_all)
    cc = cc.sort_values([*keys, "n", "country"], ascending=[True, True, False, True]).drop_duplicates(keys)
    fd = agg.join(cc.set_index(keys).country).reset_index()
    fd["modis"] = fd.terra | fd.aqua
    fd["modis_np"] = fd.terra_np | fd.aqua_np
    return fd[["cell_id", "date", "country", *FLAGS, *(f"{f}_np" for f in FLAGS), "persistent"]]


def build_segments(cfg: dict, outages: pd.DataFrame) -> pd.DataFrame:
    cov = {k: (as_date(a), as_date(b)) for k, (a, b) in cfg["coverage"].items()}
    first = min(a for a, _ in cov.values()).replace(day=1)
    last = pd.Period(str(cfg["years"]["display_last_month"])[:7], "M").end_time.normalize()
    days = pd.DataFrame({"date": pd.date_range(first, last)})
    days["year"], days["month"] = days.date.dt.year, days.date.dt.month
    days["seg"] = segment_of(days.date, boundaries(cfg))
    sat_cov = satellite_coverage(cfg)
    flagged = outages[outages.flagged]
    for sat, (a, b) in sat_cov.items():
        col = SATS[sat]
        days[f"{col}_on"] = days.date.between(pd.Timestamp(a), pd.Timestamp(b))
        out_days = set(flagged.date[flagged.satellite == sat])
        days[f"gap_{col}"] = days[f"{col}_on"] & days.date.isin(out_days)
    for col in GAP_COLS:                      # satellites without coverage (not configured)
        if f"{col}_on" not in days:
            days[f"{col}_on"], days[f"gap_{col}"] = False, False
    days["modis_on"] = days.terra_on | days.aqua_on
    g = days.groupby(["year", "month", "seg"])
    seg = g.agg(start=("date", "min"), end=("date", "max"), ndays=("date", "size"),
                **{f"{c}_days": (f"{c}_on", "sum") for c in DAY_COLS},
                **{f"gap_{c}": (f"gap_{c}", "sum") for c in GAP_COLS}).reset_index()
    seg["terra_only"] = (seg.aqua_days == 0) & (seg.terra_days > 0)
    seg["viirs_era"] = seg.start >= pd.Timestamp(as_date(cfg["sensors"]["viirs_start"]))
    c = continuation(cfg)
    # continuation era: from the switch the VIIRS value comes from the continuation satellite
    seg["cont_era"] = seg.start >= pd.Timestamp(c["switch_date"]) if c else False
    seg["month_days"] = seg.groupby(["year", "month"]).ndays.transform("sum")
    return seg


def run(cfg: dict, region_name: str) -> pd.DataFrame:
    det = read_stage(cfg, region_name, "detections_clean")
    outages = read_stage(cfg, region_name, "outages")
    size = cfg["grid"]["size_deg"]
    fd = build_fire_days(det, persistent_mask(cfg, region_name, det), size)
    seg = build_segments(cfg, outages)
    fd["year"], fd["month"] = fd.date.dt.year.astype(np.int16), fd.date.dt.month.astype(np.int8)
    fd["seg"] = segment_of(fd.date, boundaries(cfg))
    counts = [*FLAGS, *(f"{f}_np" for f in FLAGS)]
    fs = (fd.groupby(["cell_id", "country", "year", "month", "seg"])[counts].sum()
          .rename(columns=lambda c: f"n_{c}").reset_index())
    report = {"fire_days": len(fd), "cells": int(fd.cell_id.nunique()),
              "by_sensor": {c: int(fd[c].sum()) for c in FLAGS},
              "persistent_fire_days": int(fd.persistent.sum())}
    write_stage(cfg, region_name, "fire_days", fd, report, ["detections_clean", "persistent_sources"])
    write_stage(cfg, region_name, "fire_segments", fs, None, ["fire_days"])
    write_stage(cfg, region_name, "segments", seg, None, ["outages"])
    log.info("grid %s: %s", region_name, report)
    return fs
