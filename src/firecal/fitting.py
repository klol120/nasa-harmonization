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

from .calibration import (YearMonth, affine_factors, bootstrap_weights, choose_k, factors, fit_with_bootstrap,
                          shape_level, wape_bias, year_month_table)
from .config import path
from .geo import footprint_cells
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
    """Donor groups usable for `region`: their region is configured and shares no country with it."""
    local = set(cfg["regions"][region]["countries"])
    return {g: d for g, d in (cfg.get("donors") or {}).items()
            if d["region"] in cfg["regions"] and not local & set(d["countries"])}


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


def footprint_size(cfg: dict, countries, region: str) -> int:
    r = cfg["regions"][region]
    return len(footprint_cells(path(cfg, "boundaries"), tuple(countries), tuple(r["bbox"]), cfg["grid"]["size_deg"]))


def intercept_scale(cfg: dict, region: str, group: str) -> float:
    """Local / donor footprint cells: converts a donor's affine intercept (count per region-month)."""
    d = donor_groups(cfg, region)[group]
    return footprint_size(cfg, cfg["regions"][region]["countries"], region) / footprint_size(cfg, d["countries"], d["region"])


def fit_ab(strategy: str, local: YearMonth, donor: YearMonth | None, k, scale: float, weights=None):
    """(a, b) arrays (B, 12); b = 0 for ratio strategies."""
    if strategy.startswith("affine"):
        return affine_factors(strategy, local, donor, k, scale, weights)
    a = factors(strategy, local.sums(weights), donor.sums(weights) if donor is not None else None, k)["a"]
    return a, np.zeros_like(a)


def choose_k_ab(strategy: str, local: YearMonth, donor: YearMonth, scale: float, grid) -> tuple[float, pd.DataFrame]:
    """Leave-one-year-out WAPE over the k grid for any blended strategy (ratio or affine)."""
    rows = []
    for k in map(float, grid):
        obs, pred = [], []
        for y in local.years:
            others = [x for x in local.years if x != y]
            a, b = fit_ab(strategy, local.select(others), donor.select(others), k, scale)
            t = local.select([y])
            obs.append(t.num)
            pred.append(a[0] * t.den + b[0])
        w, bias = wape_bias(np.concatenate(obs), np.concatenate(pred))
        rows.append({"k": k, "wape_loyo": w, "bias_loyo": bias})
    t = pd.DataFrame(rows)
    return float(t.k[t.wape_loyo.idxmin()]), t


def is_blended(strategy: str) -> bool:
    return strategy.split(":")[0] in ("blend", "affine_blend", "affine_blend_a")


def fit_all(cfg: dict, region: str, spec: FitSpec, strategies: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit each strategy on spec.years. Returns (factors, bootstrap draws, k-selection table).

    factors: strategy, month, a, a_low, a_high, b, b_low, b_high, w_local, fallback, n_local_num,
    n_local_den, k. Ratio strategies have b = 0. Draws: strategy, draw, month, a, b."""
    local = table(cfg, region, spec)
    boot = cfg["calibration"]["bootstrap"]
    groups = donor_groups(cfg, region)
    W = bootstrap_weights(len(local.years), boot["n"], boot["seed"])
    lo, hi = (1 - boot["ci"]) / 2, 1 - (1 - boot["ci"]) / 2
    donors, rows, draws, ks = {}, [], [], []
    for strat in strategies:
        kind, _, g = strat.partition(":")
        donor, k, scale = None, None, 1.0
        if g:
            if g not in donors:
                donors[g] = table(cfg, groups[g]["region"], spec, groups[g]["countries"])
            donor = donors[g]
            if kind.startswith("affine"):
                scale = intercept_scale(cfg, region, g)
        if is_blended(strat):
            if kind == "blend":
                k, kt = choose_k(local, donor, cfg["calibration"]["blend_k_grid"])
            else:
                k, kt = choose_k_ab(strat, local, donor, scale, cfg["calibration"]["blend_k_grid"])
            ks.append(kt.assign(strategy=strat))
        if kind.startswith("affine"):
            a, b = fit_ab(strat, local, donor, k, scale)
            A, B = fit_ab(strat, local, donor, k, scale, W)
            nl, dl = local.sums()
            f = pd.DataFrame({"month": np.arange(1, 13), "a": a[0], "a_low": np.nanquantile(A, lo, 0),
                              "a_high": np.nanquantile(A, hi, 0), "w_local": np.nan, "fallback": False,
                              "n_local_num": nl, "n_local_den": dl})
        else:
            f, A = fit_with_bootstrap(strat, local, donor, k, boot)
            b, B = np.zeros((1, 12)), np.zeros_like(A)
        f["b"], f["b_low"], f["b_high"] = b[0], np.nanquantile(B, lo, 0), np.nanquantile(B, hi, 0)
        rows.append(f.assign(strategy=strat, k=k, intercept_scale=scale))
        d = pd.DataFrame({"draw": np.repeat(np.arange(len(A)), 12), "month": np.tile(np.arange(1, 13), len(A)),
                          "a": A.ravel(), "b": B.ravel()})
        draws.append(d.assign(strategy=strat))
    kt = pd.concat(ks, ignore_index=True) if ks else pd.DataFrame(columns=["k", "wape_loyo", "bias_loyo", "strategy"])
    return pd.concat(rows, ignore_index=True), pd.concat(draws, ignore_index=True), kt


def composite_spec(cfg: dict, strategy: str) -> dict | None:
    """{shape, level} for a composite strategy defined in calibration.composites, else None."""
    return (cfg["calibration"].get("composites") or {}).get(strategy)


def components(cfg: dict, strategy: str) -> list[str]:
    """Plain strategies a (possibly composite) strategy needs fitted."""
    c = composite_spec(cfg, strategy)
    return [c["shape"], c["level"]] if c else [strategy]


def fit_point(cfg: dict, region: str, strategy: str, years, exclude_persistent: bool):
    """Point (a, b, k) of a plain strategy fitted on `years` (k chosen by leave-one-year-out there)."""
    kind, _, g = strategy.partition(":")
    local = table(cfg, region, FitSpec("a", years, exclude_persistent))
    donor, scale, k = None, 1.0, None
    if g:
        d = donor_groups(cfg, region)[g]
        donor = table(cfg, d["region"], FitSpec("a", years, exclude_persistent), d["countries"])
        if kind.startswith("affine"):
            scale = intercept_scale(cfg, region, g)
    if is_blended(strategy):
        k = (choose_k(local, donor, cfg["calibration"]["blend_k_grid"])[0] if kind == "blend"
             else choose_k_ab(strategy, local, donor, scale, cfg["calibration"]["blend_k_grid"])[0])
    a, b = fit_ab(strategy, local, donor, k, scale)
    return a[0], b[0], k


def predict_table(cfg: dict, region: str, strategy: str, fit_years, test: YearMonth, exclude_persistent: bool):
    """Predicted VIIRS per (test year, month) for any strategy, composites included. Returns (pred, k)."""
    c = composite_spec(cfg, strategy)
    if c:
        aS, bS, k = fit_point(cfg, region, c["shape"], fit_years, exclude_persistent)
        aL, bL, _ = fit_point(cfg, region, c["level"], fit_years, exclude_persistent)
        return shape_level(aS * test.den + bS, aL * test.den + bL), k
    a, b, k = fit_point(cfg, region, strategy, fit_years, exclude_persistent)
    return a * test.den + b, k
