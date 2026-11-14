"""Data-thinness thresholds from a cell-subsampling experiment (before add-country).

Step 1 (`run`): for a rich region (Greece, then EastMed) keep a random fraction of its cells (50, 20,
10, 5, 2 %; 50 repetitions each; seeds recorded), and for each subsample fit and score
  local    per-month local ratios
  single   one local ratio
  blend    local shrunk to the donor, k by leave-one-year-out on the fit years
  donor    the donor pool's monthly ratios
  lebanon  the Lebanon strategy: monthly shape from affine_blend:<donor>, annual level from single
on both hold-out folds (fit 2012-16 / test 2017-20 and reverse; region monthly totals) and on the
continuity check at 2012 (step index with the factor-bootstrap x year-spread band, as in validate).

The donor is disjoint from the subsampled region: eastmed_pool for Greece (Lebanon's pool), all of
Greece for EastMed. Fitting uses the same inputs as the pipeline (usable dates, persistent fire-days
excluded). Subsamples draw from the cells that have at least one fire-day in the record; cells that
never burn add nothing to any sum, so this equals sampling the footprint.

Step 2 (`analyze`): see tools/thresholds_analysis.py.

Run: .venv/bin/python tools/thresholds_experiment.py [--regions greece eastmed] [--reps 50]
Writes docs/reports/thresholds_data/{region}_{months,runs}.csv.gz
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from firecal.calibration import (YearMonth, affine_factors, bootstrap_weights, factors, shape_level, wape_bias)
from firecal.config import load_config
from firecal.fitting import FitSpec, ensure_fire_days, footprint_size, table, usable_dates
from firecal.io import read_stage

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/reports/thresholds_data"
FRACTIONS = [1.0, 0.5, 0.2, 0.1, 0.05, 0.02]
STRATEGIES = ["local", "single", "blend", "donor", "lebanon"]
DONORS = {"greece": ("eastmed", ["Cyprus", "Turkey", "Syria", "Israel", "Palestine"], "eastmed_pool"),
          "eastmed": ("greece", ["Greece"], "greece")}
BEFORE, AFTER = [2009, 2010, 2011], [2012, 2013, 2014]
N_BOOT = 200          # continuity band draws per subsample (validate uses 1000 on one fit)


# ---------------------------------------------------------------- cell-level inputs

def cell_inputs(cfg, region, years, excl):
    """Per-cell arrays for fitting (usable dates) and continuity (segments)."""
    sfx = "_np" if excl else ""
    fd = ensure_fire_days(cfg, region)
    cells = np.array(sorted(fd.cell_id.astype(str).unique()))
    idx = {c: i for i, c in enumerate(cells)}
    use = fd[usable_dates(cfg, fd, read_stage(cfg, region, "outages"), ["Terra", "Aqua", "SNPP"])]
    use = use[use.date.dt.year.isin(years)]
    g = use.groupby([use.cell_id.astype(str), use.date.dt.year, use.date.dt.month])[[f"viirs{sfx}", f"modis{sfx}"]].sum()
    V = np.zeros((len(cells), len(years), 12))
    M = np.zeros_like(V)
    ci = g.index.get_level_values(0).map(idx).to_numpy()
    yi = g.index.get_level_values(1).to_numpy() - years[0]
    mi = g.index.get_level_values(2).to_numpy() - 1
    V[ci, yi, mi] = g[f"viirs{sfx}"].to_numpy()
    M[ci, yi, mi] = g[f"modis{sfx}"].to_numpy()

    # continuity: 2009-2014 from segments (exact January 2012 split), as validate.continuity
    fs = read_stage(cfg, region, "fire_segments")
    seg = read_stage(cfg, region, "segments")
    cy = BEFORE + AFTER
    fs = fs[fs.year.isin(cy)].merge(seg[["year", "month", "seg", "viirs_era"]], on=["year", "month", "seg"])
    shape = (len(cells), len(cy), 12)
    Mest, Vobs, Mall = np.zeros(shape), np.zeros(shape), np.zeros(shape)
    ci = fs.cell_id.astype(str).map(idx).to_numpy()
    ok = ~pd.isna(ci)
    fs, ci = fs[ok], ci[ok].astype(int)
    yi, mi = fs.year.to_numpy() - cy[0], fs.month.to_numpy() - 1
    era = fs.viirs_era.to_numpy()
    np.add.at(Mall, (ci, yi, mi), fs[f"n_modis{sfx}"].to_numpy())
    np.add.at(Mest, (ci[~era], yi[~era], mi[~era]), fs[f"n_modis{sfx}"].to_numpy()[~era])
    np.add.at(Vobs, (ci[era], yi[era], mi[era]), fs[f"n_viirs{sfx}"].to_numpy()[era])
    s = seg[seg.year.isin(cy) & ~seg.viirs_era]
    frac = np.zeros((len(cy), 12))
    np.add.at(frac, (s.year.to_numpy() - cy[0], s.month.to_numpy() - 1), (s.ndays / s.month_days).to_numpy())
    return cells, V, M, Mest, Vobs, Mall, frac


# ---------------------------------------------------------------- models

def choose_k(kind, local, donor, scale, grid):
    """Leave-one-year-out WAPE of monthly totals over the k grid (blend or affine_blend)."""
    best = None
    for k in map(float, grid):
        obs, pred = [], []
        for y in local.years:
            o = [x for x in local.years if x != y]
            a, b = fit(kind, local.select(o), donor.select(o), k, scale)
            t = local.select([y])
            obs.append(t.num)
            pred.append(a[0] * t.den + b[0])
        w, _ = wape_bias(np.concatenate(obs), np.concatenate(pred))
        if not np.isnan(w) and (best is None or w < best[1]):
            best = (k, w)
    return best[0] if best else float(grid[-1])


def fit(kind, local, donor, k, scale, weights=None):
    """(a, b) arrays (B, 12) for one plain model."""
    if kind == "affine_blend":
        return affine_factors("affine_blend:x", local, donor, k, scale, weights)
    strat = {"local": "local", "single": "single", "blend": "blend:x", "donor": "donor:x"}[kind]
    with np.errstate(invalid="ignore", divide="ignore"):
        a = factors(strat, local.sums(weights), donor.sums(weights), k)["a"]
    return a, np.zeros_like(a)


class Model:
    """A fitted strategy: point (a, b) and, for `lebanon`, the level model's (aL, bL)."""

    def __init__(self, strategy, local, donor, scale, grid, weights=None, k=None):
        self.strategy = strategy
        if strategy == "lebanon":
            self.k = choose_k("affine_blend", local, donor, scale, grid) if k is None else k
            self.a, self.b = fit("affine_blend", local, donor, self.k, scale, weights)
            self.aL, self.bL = fit("single", local, donor, None, scale, weights)
        else:
            self.k = (choose_k("blend", local, donor, scale, grid) if k is None else k) if strategy == "blend" else None
            self.a, self.b = fit(strategy, local, donor, self.k, scale, weights)

    def predict(self, den, frac=1.0, est_mask=None):
        """den (ny, 12) -> prediction (B, ny, 12); composite rescaled per year over est_mask months."""
        p = self.a[:, None, :] * den[None] + self.b[:, None, :] * frac
        if self.strategy != "lebanon":
            return p
        lv = self.aL[:, None, :] * den[None] + self.bL[:, None, :] * frac
        m = np.ones_like(den, bool) if est_mask is None else est_mask
        s = np.where(m, p, 0).sum(-1, keepdims=True)
        l = np.where(m, lv, 0).sum(-1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.where(s > 0, l / np.where(s > 0, s, 1), np.nan)
        return np.where(m, np.where(s > 0, p * r, lv), p)


# ---------------------------------------------------------------- one subsample

def evaluate(cfg, keep, inp, donor_tabs, years, scale, grid):
    cells, V, M, Mest, Vobs, Mall, frac = inp
    h = cfg["calibration"]["holdout"]
    fit_y = np.arange(h["fit"][0], h["fit"][1] + 1)
    test_y = np.arange(h["test"][0], h["test"][1] + 1)
    Vs, Ms = V[keep].sum(0), M[keep].sum(0)
    local = YearMonth(years, Vs, Ms)
    months, runs = [], {}
    for fold, (fy, ty) in {"forward": (fit_y, test_y), "reverse": (test_y, fit_y)}.items():
        lf, lt = local.select(fy), local.select(ty)
        df = donor_tabs.select(fy)
        for s in STRATEGIES:
            mdl = Model(s, lf, df, scale, grid)
            pred = mdl.predict(lt.den)[0]
            err = pred - lt.num
            for m in range(12):
                months.append({"strategy": s, "fold": fold, "month": m + 1, "obs": lt.num[:, m].sum(),
                               "abs_err": np.abs(err[:, m]).sum(), "err": err[:, m].sum()})
            w, b = wape_bias(lt.num, pred) if lt.num.sum() > 0 else (np.nan, np.nan)
            runs[f"{s}_wape_{fold}"], runs[f"{s}_bias_{fold}"] = w, b
            if mdl.k is not None:
                runs[f"{s}_k_{fold}"] = mdl.k

    # continuity on the overlap fit (as validate.continuity)
    Me, Vo, Ma = Mest[keep].sum(0), Vobs[keep].sum(0), Mall[keep].sum(0)
    est_mask = frac > 0                      # months with an estimated (pre-VIIRS) segment
    yb, ya = slice(0, 3), slice(3, 6)
    m_step = Ma[ya].sum() / Ma[yb].sum() if Ma[yb].sum() > 0 else np.nan
    Wb = bootstrap_weights(len(years), N_BOOT, cfg["calibration"]["bootstrap"]["seed"])
    rng = np.random.default_rng(cfg["calibration"]["bootstrap"]["seed"])
    for s in STRATEGIES:
        pt = Model(s, local, donor_tabs, scale, grid)
        dr = Model(s, local, donor_tabs, scale, grid, weights=Wb, k=pt.k)

        def step(mdl):
            est = np.where(est_mask, mdl.predict(Me, frac, est_mask), 0)
            H = est + Vo
            with np.errstate(invalid="ignore", divide="ignore"):
                return (H[:, ya].sum((1, 2)) / H[:, yb].sum((1, 2))) / m_step

        idx = float(step(pt)[0])
        draws = step(dr)
        py = pt.predict(Ms)[0].sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            opy = Vs.sum(1) / py
        opy = opy[np.isfinite(opy)]
        if len(opy) and np.isfinite(draws).any():
            noise = rng.choice(opy, (len(draws), 3)).mean(1) / opy.mean()
            lo, hi = np.nanquantile(draws * noise, [0.05, 0.95])
        else:
            lo = hi = np.nan
        runs[f"{s}_step"] = idx
        runs[f"{s}_band_lo"], runs[f"{s}_band_hi"] = lo, hi
        runs[f"{s}_cont_pass"] = bool(lo <= 1 <= hi) if np.isfinite(lo) else False
        if pt.k is not None:
            runs[f"{s}_k_overlap"] = pt.k

    n_month = Ms.sum(0)                      # local MODIS fire-days per calendar month, overlap years
    runs.update({f"n_m{m + 1}": n_month[m] for m in range(12)})
    runs.update({"n_total": Ms.sum(), "n_annual": Ms.sum() / len(years), "v_total": Vs.sum(), "n_cells": int(keep.sum())})
    return pd.DataFrame(months), runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", nargs="+", default=["greece", "eastmed"])
    ap.add_argument("--reps", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261114)
    args = ap.parse_args()
    cfg = load_config()
    excl = cfg["persistence"]["exclude_from_calibration"]
    y0, y1 = cfg["calibration"]["overlap_years"]
    years = np.arange(y0, y1 + 1)
    grid = cfg["calibration"]["blend_k_grid"]
    OUT.mkdir(parents=True, exist_ok=True)
    for ri, region in enumerate(args.regions):
        t0 = time.time()
        d_region, d_countries, d_name = DONORS[region]
        donor = table(cfg, d_region, FitSpec("a", list(years), excl), d_countries)
        inp = cell_inputs(cfg, region, years, excl)
        n_cells = len(inp[0])
        foot = footprint_size(cfg, cfg["regions"][region]["countries"], region)
        foot_d = footprint_size(cfg, d_countries, d_region)
        all_m, all_r = [], []
        for frac in FRACTIONS:
            for rep in range(1 if frac == 1.0 else args.reps):
                seed = [args.seed, ri, int(round(frac * 1000)), rep]
                rng = np.random.default_rng(seed)
                keep = np.zeros(n_cells, bool)
                keep[rng.choice(n_cells, max(1, int(round(frac * n_cells))), replace=False)] = True
                scale = frac * foot / foot_d           # intercept per region-month: subsample / donor footprint
                mo, ru = evaluate(cfg, keep, inp, donor, years, scale, grid)
                ident = {"region": region, "frac": frac, "rep": rep, "seed": json.dumps(seed)}
                all_m.append(mo.assign(**ident))
                all_r.append({**ident, **ru})
            print(f"{region} {frac:.0%}: {time.time() - t0:.0f}s", flush=True)
        pd.concat(all_m).to_csv(OUT / f"{region}_months.csv.gz", index=False)
        runs = pd.DataFrame(all_r)
        runs.to_csv(OUT / f"{region}_runs.csv.gz", index=False)
        meta = {"region": region, "donor": d_name, "cells_sampled_from": n_cells, "footprint_cells": foot,
                "donor_footprint_cells": foot_d, "fractions": FRACTIONS, "reps": args.reps, "seed": args.seed,
                "seed_rule": "numpy default_rng([seed, region_index, round(frac*1000), rep])",
                "region_index": ri, "n_boot_continuity": N_BOOT, "exclude_persistent": excl,
                "holdout": cfg["calibration"]["holdout"], "overlap_years": [y0, y1], "k_grid": grid}
        (OUT / f"{region}_meta.json").write_text(json.dumps(meta, indent=1))
        print(f"{region}: done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
