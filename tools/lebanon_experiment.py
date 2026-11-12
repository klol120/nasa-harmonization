"""Lebanon experiment before Phase 5: ratio vs affine transfer, zero-MODIS share, bias by year,
continuity under the old (factor bootstrap only) and new (with year-to-year spread) bands.

Run: .venv/bin/python tools/lebanon_experiment.py [--region lebanon]
Writes docs/reports/{region}_experiment.md. Uses the config's persistence rule (default: persistent
cells excluded from fitting, the same rule in donors).
"""
from __future__ import annotations

import argparse
from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd

from firecal.calibration import (affine_factors, bootstrap_weights, factors, wape_bias)
from firecal.config import load_config, path, region_settings
from firecal.fitting import FitSpec, donor_groups, ensure_fire_days, table, usable_dates
from firecal.geo import _boundaries
from firecal.io import read_stage
from firecal.stages.validate import region_segments


# ---------- models ----------

def fit(strategy, local, donor, k, scale, weights=None):
    """(a, b) arrays (B, 12) for ratio strategies (b = 0) and affine strategies."""
    if strategy.startswith("affine"):
        return affine_factors(strategy, local, donor, k, scale, weights)
    ls = local.sums(weights)
    ds = donor.sums(weights) if donor is not None else None
    a = factors(strategy, ls, ds, k)["a"]
    return a, np.zeros_like(a)


def needs_k(strategy):
    return strategy.split(":")[0] in ("blend", "affine_blend", "affine_blend_a")


def choose_k(strategy, local, donor, scale, grid):
    best = None
    for k in map(float, grid):
        obs, pred = [], []
        for y in local.years:
            others = [x for x in local.years if x != y]
            a, b = fit(strategy, local.select(others), donor.select(others), k, scale)
            t = local.select([y])
            obs.append(t.num)
            pred.append(a[0] * t.den + b[0])
        w, _ = wape_bias(np.concatenate(obs), np.concatenate(pred))
        if best is None or w < best[1]:
            best = (k, w)
    return best[0]


# ---------- footprint size (for the donor intercept) ----------

@lru_cache(maxsize=None)
def footprint_cells(boundaries: str, countries: tuple, bbox: tuple, size: float) -> int:
    w, s, e, n = bbox
    lats = np.arange(np.floor(s / size) * size + size / 2, n, size)
    lons = np.arange(np.floor(w / size) * size + size / 2, e, size)
    lo, la = np.meshgrid(lons, lats)
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lo.ravel(), la.ravel()), crs=4326)
    ne = _boundaries(boundaries)
    poly = ne[ne.ADMIN.isin(countries)]
    return int(gpd.sjoin(pts, poly, predicate="within").index.nunique())


# ---------- experiment ----------

def strategies_for(cfg, region):
    groups = list(donor_groups(cfg, region))
    out = ["single", "local"] + [f"{k}:{g}" for k in ("donor", "pooled", "blend") for g in groups]
    out += ["affine_local"] + [f"{k}:{g}" for k in ("affine_blend", "affine_blend_a") for g in groups]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="lebanon")
    region = ap.parse_args().region
    cfg = load_config()
    excl = cfg["persistence"]["exclude_from_calibration"]
    sfx = "_np" if excl else ""
    size = cfg["grid"]["size_deg"]
    groups = donor_groups(cfg, region)
    r = cfg["regions"][region]
    bnd = str(path(cfg, "boundaries"))
    n_local = footprint_cells(bnd, tuple(r["countries"]), tuple(r["bbox"]), size)
    scale = {g: n_local / footprint_cells(bnd, tuple(d["countries"]), tuple(cfg["regions"][d["region"]]["bbox"]), size)
             for g, d in groups.items()}
    grid_k = cfg["calibration"]["blend_k_grid"]
    h = cfg["calibration"]["holdout"]
    fit_y = list(range(h["fit"][0], h["fit"][1] + 1))
    test_y = list(range(h["test"][0], h["test"][1] + 1))
    ov = list(range(cfg["calibration"]["overlap_years"][0], cfg["calibration"]["overlap_years"][1] + 1))

    def tables(years):
        loc = table(cfg, region, FitSpec("a", years, excl))
        don = {g: table(cfg, d["region"], FitSpec("a", years, excl), d["countries"]) for g, d in groups.items()}
        return loc, don

    tabs = {"fit": tables(fit_y), "test": tables(test_y), "ov": tables(ov)}
    rs = region_segments(cfg, region).rename(columns={f"n_modis{sfx}": "M", f"n_viirs{sfx}": "V"})
    before, after = [2009, 2010, 2011], [2012, 2013, 2014]
    m_step = (rs[rs.year.isin(after)].M.sum()) / (rs[rs.year.isin(before)].M.sum())
    boot = cfg["calibration"]["bootstrap"]
    W = bootstrap_weights(len(ov), boot["n"], boot["seed"])

    def h_mean(years, a, b):
        s = rs[rs.year.isin(years)]
        m = s.month.to_numpy() - 1
        est = a[m] * s.M.to_numpy() + b[m] * (s.ndays / s.month_days).to_numpy()
        return np.where(s.viirs_era, s.V, est).sum() / len(years)

    rows, by_year = [], []
    for strat in strategies_for(cfg, region):
        g = strat.partition(":")[2] or None
        rec = {"strategy": strat, "scale": scale.get(g)}
        for fold, (fa, ta) in {"forward": ("fit", "test"), "reverse": ("test", "fit")}.items():
            lf, dfit = tabs[fa][0], tabs[fa][1].get(g)
            lt = tabs[ta][0]
            k = choose_k(strat, lf, dfit, scale.get(g, 1), grid_k) if needs_k(strat) else None
            a, b = fit(strat, lf, dfit, k, scale.get(g, 1))
            pred = a[0] * lt.den + b[0]
            rec[f"wape_{fold}"], rec[f"bias_{fold}"] = wape_bias(lt.num, pred)
            rec[f"k_{fold}"] = k
            for i, y in enumerate(lt.years):
                by_year.append({"strategy": strat, "fold": fold, "year": int(y), "obs": lt.num[i].sum(),
                                "pred": pred[i].sum()})
        # continuity: fit on the whole overlap, bootstrap years
        lo_, do_ = tabs["ov"][0], tabs["ov"][1].get(g)
        k = choose_k(strat, lo_, do_, scale.get(g, 1), grid_k) if needs_k(strat) else None
        a, b = fit(strat, lo_, do_, k, scale.get(g, 1))
        a, b = a[0], b[0]
        idx = h_mean(after, a, b) / h_mean(before, a, b) / m_step
        A, B = fit(strat, lo_, do_, k, scale.get(g, 1), W)
        draws = np.array([h_mean(after, A[i], B[i]) / h_mean(before, A[i], B[i]) / m_step for i in range(len(W))])
        o = rs[rs.year.isin(ov) & rs.viirs_era]
        mm = o.month.to_numpy() - 1
        o = o.assign(pred=a[mm] * o.M.to_numpy() + b[mm] * (o.ndays / o.month_days).to_numpy())
        py = o.groupby("year")[["pred", "V"]].sum()
        obs_pred = (py.V / py.pred).to_numpy()
        rng = np.random.default_rng(boot["seed"])          # same noise draws for every strategy
        noise = rng.choice(obs_pred, (len(draws), 3)).mean(1) / obs_pred.mean()
        old = np.nanquantile(draws, [0.05, 0.95])
        new = np.nanquantile(draws * noise, [0.05, 0.95])
        rec.update({"k_overlap": k, "step_index": idx, "old_band": old, "new_band": new,
                    "flag_old": not old[0] <= 1 <= old[1], "flag_new": not new[0] <= 1 <= new[1],
                    "insample_pred_over_obs": float(py.pred.sum() / py.V.sum())})
        rows.append(rec)
    res = pd.DataFrame(rows)
    # Ranking (continuity and bias first, WAPE second):
    #  1. continuity not flagged under the new band;
    #  2. score = |step index - 1| + mean(|forward bias|, |reverse bias|)  (both hold-out folds: one
    #     4-year fold alone is too noisy for Lebanon);
    #  3. forward WAPE.
    res["bias_both"] = (res.bias_forward.abs() + res.bias_reverse.abs()) / 2
    res["score"] = (res.step_index - 1).abs() + res.bias_both
    res = res.sort_values(["flag_new", "score", "wape_forward"]).reset_index(drop=True)
    by_year = pd.DataFrame(by_year)

    # zero-MODIS share of VIIRS fire-days per month (overlap, usable days)
    fd = ensure_fire_days(cfg, region)
    fd = fd[usable_dates(cfg, fd, read_stage(cfg, region, "outages"), ["Terra", "Aqua", "SNPP"])]
    fd = fd[fd.date.dt.year.isin(ov)]
    v = fd[fd[f"viirs{sfx}"]]
    zs = v.assign(zero=~v[f"modis{sfx}"]).groupby(v.date.dt.month).agg(viirs=("zero", "size"), zero_modis=("zero", "sum"))
    zs["share"] = zs.zero_modis / zs.viirs
    mod = fd[fd[f"modis{sfx}"]].groupby(fd.date.dt.month).size().reindex(range(1, 13), fill_value=0)
    zs["modis_fire_days"] = mod
    write_report(cfg, region, res, by_year, zs, scale, n_local, excl)
    print(res[["strategy", "step_index", "flag_new", "bias_forward", "wape_forward"]].head(12).round(3).to_string())


def write_report(cfg, region, res, by_year, zs, scale, n_local, excl):
    out = path(cfg, "reports") / f"{region}_experiment.md"
    L = [f"# {region}: ratio vs affine transfer (experiment, before Phase 5)", "",
         f"Persistence rule: {'persistent cells excluded from fitting (local and donors)' if excl else 'PDF rules'}. "
         f"Hold-out fit {cfg['calibration']['holdout']['fit']}, test {cfg['calibration']['holdout']['test']}; "
         "k chosen by leave-one-year-out on the fit years (on the overlap for continuity).", "",
         f"Affine donor intercepts are scaled by footprint size: {region} has {n_local} cells; scale = "
         + ", ".join(f"{g} {s:.3f}" for g, s in scale.items()) + ".", "",
         "Ranked by (1) continuity not flagged under the new band, (2) score = |step index − 1| + "
         "mean(|forward bias|, |reverse bias|), (3) forward WAPE.", "",
         "| rank | strategy | step index | old band (factor bootstrap) | new band (+ year spread) | forward bias | forward WAPE | reverse bias | reverse WAPE | score | in-sample pred/obs | k (fwd / overlap) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, x in res.iterrows():
        fo = "**flag**" if x.flag_old else "ok"
        fn = "**flag**" if x.flag_new else "ok"
        k = "" if x.k_forward is None or pd.isna(x.k_forward) else f"{x.k_forward:g} / {x.k_overlap:g}"
        L.append(f"| {i + 1} | {x.strategy} | {x.step_index:.3f} | [{x.old_band[0]:.2f}, {x.old_band[1]:.2f}] {fo} | "
                 f"[{x.new_band[0]:.2f}, {x.new_band[1]:.2f}] {fn} | {x.bias_forward:+.1%} | {x.wape_forward:.3f} | "
                 f"{x.bias_reverse:+.1%} | {x.wape_reverse:.3f} | {x.score:.3f} | {x.insample_pred_over_obs:.2f} | {k} |")
    top = list(res.strategy.head(4)) + [s for s in ("local", "blend:eastmed_pool") if s not in list(res.strategy.head(4))]
    L += ["", "## Hold-out bias by year", "", "bias = (pred − obs) / obs for each test year.", "",
          "| strategy | " + " | ".join(str(y) for y in range(2012, 2021)) + " |", "|---|" + "---|" * 9]
    for s in top:
        b = by_year[by_year.strategy == s].set_index("year")
        L.append(f"| {s} | " + " | ".join(f"{(b.pred[y] - b.obs[y]) / b.obs[y]:+.0%}" for y in range(2012, 2021)) + " |")
    obs = by_year[(by_year.strategy == "local")].set_index("year").obs
    L.append("| *observed VIIRS fire-days* | " + " | ".join(f"{obs[y]:.0f}" for y in range(2012, 2021)) + " |")
    L += ["", "(2012-2016 from the reverse fold, 2017-2020 from the forward fold.)", "",
          "## VIIRS fire-days in cell-days with no MODIS detection (2012-2020)", "",
          "| month | VIIRS fire-days | of which MODIS zero | share | MODIS fire-days |", "|---|---|---|---|---|"]
    for m, x in zs.iterrows():
        L.append(f"| {m} | {x.viirs} | {x.zero_modis} | {x.share:.0%} | {x.modis_fire_days} |")
    lc = region_settings(cfg, "low_confidence", region)
    flag = (zs.modis_fire_days < lc["min_modis_fire_days"]) | (zs.share >= lc["max_zero_modis_share"])
    L += ["", "## low_confidence rule (applied in export)", "",
          f"A pre-2012 (estimated) month is `low_confidence` when its calendar month has, on the overlap years, "
          f"fewer than {lc['min_modis_fire_days']} local MODIS fire-days (the factor rests on too few MODIS "
          f"observations) or at least {lc['max_zero_modis_share']:.0%} of VIIRS fire-days in cell-days without "
          "any MODIS detection (the activity is almost invisible to MODIS, so the estimate cannot see it).", "",
          f"{region}: flagged calendar months = " + (", ".join(str(m) for m in zs.index[flag]) or "none") + "."]
    out.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
