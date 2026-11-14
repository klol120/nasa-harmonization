"""Anomalies: z-score of harmonized fire-days against a per-cell, per-calendar-month baseline.

z = (H - mean) / max(sd, min_sd), with mean and sd (ddof=1) over anomalies.baseline_years, using rows
with data_available and not display_only. z is null when sd = 0 (and min_sd = 0) or H is null;
display-only rows (2026) are scored against the same baseline. The same is done for region totals.
Sensitivity: z under each anomalies.sensitivity_baselines, compared with the main z.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import path, region_settings
from ..io import read_stage, write_stage

log = logging.getLogger(__name__)
SUM_COLS = ["modis_raw", "viirs_raw", "noaa20_raw", "harmonized", "harmonized_low", "harmonized_high"]
OR_COLS = ["is_estimate", "has_gap", "partial_month", "display_only", "low_confidence"]


def zscore(df: pd.DataFrame, keys: list[str], years, min_sd: float) -> tuple[pd.Series, pd.DataFrame]:
    y0, y1 = years
    base = df[df.year.between(y0, y1) & df.data_available & ~df.display_only]
    b = base.groupby([*keys, "month"], observed=True).harmonized.agg(mean="mean", sd="std", n="count").reset_index()
    m = df[[*keys, "month", "harmonized"]].merge(b, on=[*keys, "month"], how="left")
    sd = np.maximum(m.sd.fillna(0).to_numpy(), min_sd)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(sd > 0, (m.harmonized.to_numpy() - m["mean"].to_numpy()) / np.where(sd > 0, sd, 1), np.nan)
    return pd.Series(z, index=df.index, dtype="float32"), b


def region_monthly(h: pd.DataFrame) -> pd.DataFrame:
    """Sum cells per month; flags combined with OR, data_available with AND (docs/data_contract.md)."""
    g = h.groupby(["year", "month"])
    r = g[SUM_COLS].sum(min_count=1)
    r[OR_COLS] = g[OR_COLS].any()
    r["data_available"] = g.data_available.all()
    r["source"] = g.source.first()                 # region-wide: identical for every cell
    r["n_cells"] = g.size()
    r = r.reset_index()
    for c in ("harmonized", "harmonized_low", "harmonized_high"):
        r[c] = r[c].where(r.data_available)
    return r


def compare(z_main: pd.Series, z_alt: pd.Series, mask: pd.Series) -> dict:
    ok = mask & z_main.notna() & z_alt.notna()
    a, b = z_main[ok].astype(float), z_alt[ok].astype(float)
    big_a, big_b = a.abs() > 2, b.abs() > 2
    return {"rows": int(ok.sum()), "corr_z": float(np.corrcoef(a, b)[0, 1]) if ok.sum() > 2 else None,
            "mean_abs_dz": float((a - b).abs().mean()), "median_abs_dz": float((a - b).abs().median()),
            "share_flip_abs_z_gt_2": float((big_a != big_b).mean()),
            "abs_z_gt_2_main": int(big_a.sum()), "abs_z_gt_2_alt": int(big_b.sum())}


def run(cfg: dict, region_name: str) -> pd.DataFrame:
    a = region_settings(cfg, "anomalies", region_name)
    h = read_stage(cfg, region_name, "harmonized")
    h["anomaly_z"], base = zscore(h, ["cell_id"], a["baseline_years"], a["min_sd"])
    r = region_monthly(h)
    r["anomaly_z"], rbase = zscore(r.assign(_r=0), ["_r"], a["baseline_years"], a["min_sd"])

    sens = []
    for alt in a.get("sensitivity_baselines", []):
        z_alt, _ = zscore(h, ["cell_id"], alt, a["min_sd"])
        rz_alt, _ = zscore(r.assign(_r=0), ["_r"], alt, a["min_sd"])
        sens.append({"baseline_years": alt,
                     "cells_all_months": compare(h.anomaly_z, z_alt, pd.Series(True, index=h.index)),
                     "cells_pre2012": compare(h.anomaly_z, z_alt, h.year < 2012),
                     "cells_2012_on": compare(h.anomaly_z, z_alt, h.year >= 2012),
                     "region": compare(r.anomaly_z, rz_alt, pd.Series(True, index=r.index)),
                     "region_mean_abs_dz_2026": float((r.anomaly_z - rz_alt)[r.display_only].abs().mean())
                     if r.display_only.any() else None})
    report = {"baseline_years": a["baseline_years"], "sensitivity": sens,
              "cells_with_z": int(h.groupby("cell_id", observed=True).anomaly_z.count().gt(0).sum())}
    write_report(cfg, region_name, report)
    write_stage(cfg, region_name, "anomalies", h, report, ["harmonized"])
    write_stage(cfg, region_name, "region_monthly", r, None, ["harmonized"])
    write_stage(cfg, region_name, "baseline", base, None, ["harmonized"])
    log.info("anomalies %s: %s", region_name, [s["region"] for s in sens])
    return h


def write_report(cfg, region, rep) -> None:
    out = path(cfg, "reports") / f"{region}_anomalies.md"
    L = [f"# {region}: anomaly baseline sensitivity", "",
         f"Main baseline {rep['baseline_years']}. z per cell and calendar month; region z on the region total.", "",
         "| alternative baseline | scope | rows | corr(z) | mean abs Δz | median abs Δz | share flipping abs z > 2 | abs z > 2 (main / alt) |",
         "|---|---|---|---|---|---|---|---|"]
    for s in rep["sensitivity"]:
        for scope in ("region", "cells_all_months", "cells_pre2012", "cells_2012_on"):
            c = s[scope]
            corr = "" if c["corr_z"] is None else f"{c['corr_z']:.3f}"
            L.append(f"| {s['baseline_years']} | {scope} | {c['rows']} | {corr} | {c['mean_abs_dz']:.3f} | "
                     f"{c['median_abs_dz']:.3f} | {c['share_flip_abs_z_gt_2']:.1%} | {c['abs_z_gt_2_main']} / {c['abs_z_gt_2_alt']} |")
        if s["region_mean_abs_dz_2026"] is not None:
            L.append(f"\nRegion mean abs Δz for display-only months (2026): {s['region_mean_abs_dz_2026']:.3f}")
    out.write_text("\n".join(L) + "\n")
