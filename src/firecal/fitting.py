"""Assemble fitting inputs from fire_days and fit every configured strategy.

Shared by the terra (kT), calibrate (a_m) and validate stages so all three use the same rules:
- dates where every involved satellite has data (coverage) and no flagged outage;
- persistent-source fire-days excluded when persistence.exclude_from_calibration (local and donors,
  each region's own flagged cells, same rule);
- donor groups that share a country with the local region are skipped.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .calibration import YearMonth, choose_k, fit_with_bootstrap, year_month_table
from .io import read_stage, stage_file
from .outages import satellite_coverage

log = logging.getLogger(__name__)

# what each target needs: fire_days numerator/denominator columns and the satellites involved
TARGETS = {
    "a": {"num": "viirs", "den": "modis", "sats": ["Terra", "Aqua", "SNPP"]},
    "kT": {"num": "modis", "den": "terra", "sats": ["Terra", "Aqua"]},
}


@dataclass
class FitSpec:
    target: str
    years: list[int]
    exclude_persistent: bool


def ensure_fire_days(cfg: dict, region: str) -> pd.DataFrame:
    """fire_days of a region, running earlier stages if they are missing (donor regions)."""
    from .stages import clean, grid, ingest

    if not stage_file(cfg, region, "fire_days").exists():
        if not stage_file(cfg, region, "detections_clean").exists():
            if not stage_file(cfg, region, "detections").exists():
                ingest.run(cfg, region)
            clean.run(cfg, region)
        grid.run(cfg, region)
    return read_stage(cfg, region, "fire_days")


def usable_dates(cfg: dict, fire_days: pd.DataFrame, outages: pd.DataFrame, sats: list[str]) -> np.ndarray:
    cov = satellite_coverage(cfg)
    start = max(pd.Timestamp(cov[s][0]) for s in sats)
    end = min(pd.Timestamp(cov[s][1]) for s in sats)
    bad = set(outages.date[outages.flagged & outages.satellite.isin(sats)])
    return (fire_days.date.between(start, end) & ~fire_days.date.isin(bad)).to_numpy()


def table(cfg: dict, region: str, spec: FitSpec, countries: list[str] | None = None) -> YearMonth:
    t = TARGETS[spec.target]
    fd = ensure_fire_days(cfg, region)
    outages = read_stage(cfg, region, "outages")
    fd = fd[usable_dates(cfg, fd, outages, t["sats"])]
    if countries is not None:
        fd = fd[fd.country.isin(countries)]
    sfx = "_np" if spec.exclude_persistent else ""
    return year_month_table(fd, t["num"] + sfx, t["den"] + sfx, spec.years)


def donor_groups(cfg: dict, region: str) -> dict:
    local = set(cfg["regions"][region]["countries"])
    return {g: d for g, d in cfg.get("donors", {}).items() if not local & set(d["countries"])}


def expand_strategies(cfg: dict, region: str, patterns: list[str]) -> list[str]:
    groups = list(donor_groups(cfg, region))
    out = []
    for p in patterns:
        kind, _, g = p.partition(":")
        if not g:
            out.append(kind)
        else:
            out += [f"{kind}:{x}" for x in (groups if g == "*" else [g]) if x in groups]
    return out


def chosen(cfg: dict, section: str, region: str, default: str = "local") -> str:
    s = cfg[section].get("strategy", default)
    return s.get(region, default) if isinstance(s, dict) else s


def fit_all(cfg: dict, region: str, spec: FitSpec, strategies: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit each strategy on spec.years. Returns (factors, boot draws, k-selection table)."""
    local = table(cfg, region, spec)
    boot = cfg["calibration"]["bootstrap"]
    groups = donor_groups(cfg, region)
    donors = {}
    rows, draws, ks = [], [], []
    for strat in strategies:
        kind, _, g = strat.partition(":")
        donor, k = None, None
        if g:
            if g not in donors:
                donors[g] = table(cfg, groups[g]["region"], spec, groups[g]["countries"])
            donor = donors[g]
        if kind == "blend":
            k, kt = choose_k(local, donor, cfg["calibration"]["blend_k_grid"])
            ks.append(kt.assign(strategy=strat))
        f, d = fit_with_bootstrap(strat, local, donor, k, boot)
        rows.append(f.assign(strategy=strat, k=k))
        draws.append(pd.DataFrame(d, columns=range(1, 13)).rename_axis("draw").reset_index()
                     .melt(id_vars="draw", var_name="month", value_name="a").assign(strategy=strat))
    kt = pd.concat(ks, ignore_index=True) if ks else pd.DataFrame(columns=["k", "wape_loyo", "bias_loyo", "strategy"])
    return pd.concat(rows, ignore_index=True), pd.concat(draws, ignore_index=True), kt
