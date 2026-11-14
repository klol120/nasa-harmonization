"""Clean: vegetation fires, satellites, confidence, duplicates, persistent sources, outage flags."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .. import outages as outages_mod
from ..config import as_date, continuation, path
from ..firedays import count_by_sensor
from ..io import read_stage, stage_file, write_stage
from ..geo import cell_index
from . import ingest

log = logging.getLogger(__name__)


def _step(df: pd.DataFrame, keep, name: str, report: dict) -> pd.DataFrame:
    keep = np.asarray(keep, dtype=bool)
    report["removed"][name] = int((~keep).sum())
    return df[keep]


def sp_precedence(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    """False for NRT rows on dates the same satellite's SP product covers (SP is preferred)."""
    nrt = df.source.str.endswith("_NRT").to_numpy()
    if not nrt.any():
        return np.ones(len(df), bool)
    cov = outages_mod.satellite_coverage(cfg, sp_only=True)
    date = df.datetime_utc.dt.tz_convert(None).dt.date
    covered = np.zeros(len(df), bool)
    for sat, (a, b) in cov.items():
        covered |= (df.satellite == sat).to_numpy() & (date >= a).to_numpy() & (date <= b).to_numpy()
    return ~(nrt & covered)


def deduplicate(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    prio = {o: i for i, o in enumerate(cfg["clean"]["origin_priority"])}
    order = df.origin.astype(str).map(prio).fillna(len(prio)).to_numpy()
    ranked = df.assign(_p=order).sort_values("_p", kind="stable")
    dup = ranked.duplicated(cfg["clean"]["dedup_keys"], keep="first")
    return ~dup.reindex(df.index).to_numpy()


def persistence_stats(df: pd.DataFrame, cell_deg: float) -> pd.DataFrame:
    """Per fine cell: years active, share of available years, night share, FRP, fire-days."""
    row, col = cell_index(df.lat, df.lon, cell_deg)
    d = pd.DataFrame({"pcell": pd.Series(row).astype(str).values + "_" + pd.Series(col).astype(str).values,
                      "year": df.datetime_utc.dt.year.values,
                      "date": df.datetime_utc.dt.tz_convert(None).dt.normalize().values,
                      "night": (df.daynight == "N").values, "frp": df.frp.values,
                      "sensor": df.sensor.astype(str).values,
                      "lat": df.lat.values, "lon": df.lon.values})
    s = d.groupby("pcell").agg(years=("year", "nunique"), detections=("year", "size"),
                               night_frac=("night", "mean"), mean_frp=("frp", "mean"),
                               first=("date", "min"), last=("date", "max"))
    # Year share per sensor, over the years that sensor has data: small persistent sources are often
    # VIIRS-only, so a share over the whole MODIS era would understate them.
    s["year_frac"] = 0.0
    for sensor in ("VIIRS", "MODIS"):
        ds = d[d.sensor == sensor]
        s[f"{sensor.lower()}_fire_days"] = ds.drop_duplicates(["pcell", "date"]).groupby("pcell").size() \
            .reindex(s.index, fill_value=0)
        frac = ds.groupby("pcell").year.nunique() / max(ds.year.nunique(), 1)
        s[f"{sensor.lower()}_year_frac"] = frac.reindex(s.index, fill_value=0.0)
        s["year_frac"] = np.maximum(s["year_frac"], s[f"{sensor.lower()}_year_frac"])
    r, c = (np.array(x, dtype=int) for x in zip(*(i.split("_") for i in s.index)))
    s["lat_center"] = np.round((r + 0.5) * cell_deg - 90, 6)
    s["lon_center"] = np.round((c + 0.5) * cell_deg - 180, 6)
    return s.reset_index()


def pcells(df: pd.DataFrame, cell_deg: float) -> np.ndarray:
    row, col = cell_index(df.lat, df.lon, cell_deg)
    return pd.Series(row).astype(str).values + "_" + pd.Series(col).astype(str).values


def static_cells(df: pd.DataFrame, p: dict) -> set:
    """Fine cells whose typed detections are mostly static land sources (type 2), before rule 1."""
    typed = df[df.fire_type.notna()]
    if typed.empty:
        return set()
    share = pd.Series((typed.fire_type == 2).to_numpy()).groupby(pcells(typed, p["cell_deg"])).mean()
    return set(share.index[share >= p["static_min_share"]])


def flag_persistent(stats: pd.DataFrame, p: dict) -> pd.Series:
    return (stats.year_frac >= p["min_year_frac"]) & (stats.night_frac >= p["min_night_frac"])


def build_outages(cfg: dict) -> pd.DataFrame:
    refs = []
    for ref in cfg["gaps"]["reference_regions"]:
        if not stage_file(cfg, ref, "detections").exists():
            ingest.run(cfg, ref)
        d = read_stage(cfg, ref, "detections")
        refs.append(d[["datetime_utc", "satellite"]])
    out = outages_mod.build(cfg, pd.concat(refs, ignore_index=True))
    outages_mod.write_suspects_report(cfg, out, path(cfg, "reports") / "outage_suspects.md")
    return out


def persistence_diagnostic(cfg: dict, region_name: str, df: pd.DataFrame, stats: pd.DataFrame) -> dict:
    """Top-N cells by VIIRS fire-days and the overlap fire-day ratio with/without them. Report only."""
    p = cfg["persistence"]
    size = cfg["grid"]["size_deg"]
    y0, y1 = cfg["calibration"]["overlap_years"]
    top = stats.sort_values(["viirs_fire_days", "detections"], ascending=False).head(p["diagnostic_top_n"]).copy()
    top["flagged_by_rule"] = flag_persistent(top, p)
    ov = df[df.datetime_utc.dt.year.between(y0, y1)]
    row, col = cell_index(ov.lat, ov.lon, p["cell_deg"])
    pcell = pd.Series(row).astype(str).values + "_" + pd.Series(col).astype(str).values
    in_top = np.isin(pcell, top.pcell.values)

    def ratio(x):
        n = count_by_sensor(x, size)
        return float(n.get("VIIRS", 0) / n.get("MODIS", np.nan)), int(n.get("VIIRS", 0)), int(n.get("MODIS", 0))

    base, excl = ratio(ov), ratio(ov[~in_top])
    # coarser variant: drop the whole 0.05° pipeline cells containing a top cell
    gr, gc = cell_index(top.lat_center, top.lon_center, size)
    top_cells = set(pd.Series(gr).astype(str) + "_" + pd.Series(gc).astype(str))
    orow, ocol = cell_index(ov.lat, ov.lon, size)
    ocell = pd.Series(orow).astype(str).values + "_" + pd.Series(ocol).astype(str).values
    excl_grid = ratio(ov[~np.isin(ocell, list(top_cells))])
    report = {
        "overlap_years": [y0, y1], "cell_deg": p["cell_deg"],
        "ratio_all": base, "ratio_excl_top_fine_cells": excl, "ratio_excl_top_grid_cells": excl_grid,
        "top_cells": top.assign(first=top["first"].dt.date.astype(str), last=top["last"].dt.date.astype(str))
                        .round(3).to_dict("records"),
    }
    write_diagnostic_md(cfg, region_name, report)
    return report


def write_diagnostic_md(cfg: dict, region_name: str, rep: dict) -> None:
    out = path(cfg, "reports") / f"{region_name}_persistence_diagnostic.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    y0, y1 = rep["overlap_years"]
    lines = [
        f"# {region_name}: persistent-source diagnostic (report only, nothing removed)", "",
        f"Top {len(rep['top_cells'])} {rep['cell_deg']}° cells by VIIRS fire-days (cleaned data, all years). "
        "Check these against known open waste-burning dump sites.", "",
        "| # | lat | lon | VIIRS fire-days | MODIS fire-days | detections | years | VIIRS year share | night share | mean FRP (MW) | first | last | rule flags |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(rep["top_cells"], 1):
        lines.append(f"| {i} | {c['lat_center']:.3f} | {c['lon_center']:.3f} | {c['viirs_fire_days']} | "
                     f"{c['modis_fire_days']} | {c['detections']} | {c['years']} | {c['viirs_year_frac']:.2f} | {c['night_frac']:.2f} | "
                     f"{c['mean_frp']:.1f} | {c['first']} | {c['last']} | {'yes' if c['flagged_by_rule'] else 'no'} |")
    lines += ["", f"VIIRS/MODIS fire-day ratio ({cfg['grid']['size_deg']}° grid, {y0}-{y1}):", "",
              "| data | VIIRS fire-days | MODIS fire-days | ratio |", "|---|---|---|---|"]
    for label, key in [("all cleaned", "ratio_all"), ("without the top fine cells", "ratio_excl_top_fine_cells"),
                       ("without the grid cells containing them", "ratio_excl_top_grid_cells")]:
        r, v, m = rep[key]
        lines.append(f"| {label} | {v} | {m} | {r:.2f} |")
    out.write_text("\n".join(lines) + "\n")


def run(cfg: dict, region_name: str) -> pd.DataFrame:
    c = cfg["clean"]
    df = read_stage(cfg, region_name, "detections")
    rep = {"input": len(df), "removed": {}}
    p = cfg["persistence"]
    static = static_cells(df, p)
    df = _step(df, df.fire_type.isin(c["fire_types"]) | df.fire_type.isna(), "fire_type", rep)
    df = _step(df, ~(df.fire_type.isna().to_numpy() & np.isin(pcells(df, p["cell_deg"]), list(static))),
               "untyped_in_static_cells", rep)
    df = _step(df, df.satellite.isin(cfg["sensors"]["satellites"]), "satellite", rep)
    df = _step(df, df.confidence_class.isin(c["confidence_classes"]), "confidence", rep)
    df = _step(df, sp_precedence(df, cfg), "nrt_where_sp_exists", rep)
    df = _step(df, deduplicate(df, cfg), "duplicates", rep)
    df = _step(df, df.datetime_utc.dt.date <= max(as_date(b) for _, b in cfg["coverage"].values()),
               "after_coverage", rep)

    # Statistics on typed rows of the original constellation, so adding NRT rows (which keep static sources)
    # or the continuation satellite (NOAA-20) leaves the flagged cells unchanged; the flagged list is then
    # applied to every satellite's untyped rows. Inputs with no typed rows at all use every row.
    cont = continuation(cfg)
    base = df[df.satellite != cont["satellite"]] if cont else df
    if base.fire_type.notna().any():
        base = base[base.fire_type.notna()]
    stats = persistence_stats(base, p["cell_deg"])
    stats["flagged"] = flag_persistent(stats, p)
    if p["mode"] != "off":
        row, col = cell_index(df.lat, df.lon, p["cell_deg"])
        pcell = pd.Series(row).astype(str).values + "_" + pd.Series(col).astype(str).values
        in_flagged = np.isin(pcell, stats.pcell[stats.flagged].values)
        target = in_flagged if p["mode"] == "always" else in_flagged & df.fire_type.isna().to_numpy()
        df = _step(df, ~target, f"persistent_{p['mode']}", rep)
    else:
        rep["removed"]["persistent_off"] = 0
    rep["persistent_cells_flagged"] = int(stats.flagged.sum())
    if region_name in p.get("diagnostic_regions", []):
        rep["persistence_diagnostic"] = persistence_diagnostic(
            cfg, region_name, df[df.satellite != cont["satellite"]] if cont else df, stats)

    out = build_outages(cfg)
    rep["outage_runs"] = outages_mod.runs(out).assign(
        start=lambda x: x.start.dt.date.astype(str), end=lambda x: x.end.dt.date.astype(str)).to_dict("records")
    rep["rows"] = len(df)
    rep["by_sensor"] = df.groupby("sensor", observed=True).size().to_dict()
    df = df.reset_index(drop=True)
    write_stage(cfg, region_name, "detections_clean", df, rep, ["detections"])
    write_stage(cfg, region_name, "persistent_sources", stats[stats.years >= 2].reset_index(drop=True))
    write_stage(cfg, region_name, "outages", out, {"runs": len(rep["outage_runs"])}, cfg["gaps"]["reference_regions"])
    log.info("clean %s: %d -> %d rows %s", region_name, rep["input"], len(df), rep["removed"])
    return df
