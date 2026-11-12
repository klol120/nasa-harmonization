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

from firecal.calibration import affine_factors, bootstrap_weights, factors, shape_level, wape_bias
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


# ---------- adoption rule for affine_shape_single_level (user, 2026-11-12) ----------

def adoption(res: pd.DataFrame, composite: str, baseline: str = "single", wape_gain: float = 0.10) -> dict:
    """Adopt only if: continuity passes (new band), |bias| no worse than single's on both folds, and
    WAPE at least `wape_gain` lower than single's on both folds."""
    c = res.set_index("strategy").loc[composite]
    s = res.set_index("strategy").loc[baseline]
    tol = 1e-9
    checks = {
        "continuity_passes": bool(not c.flag_new),
        "bias_forward_no_worse": bool(abs(c.bias_forward) <= abs(s.bias_forward) + tol),
        "bias_reverse_no_worse": bool(abs(c.bias_reverse) <= abs(s.bias_reverse) + tol),
        "wape_forward_lower_by_0.10": bool(c.wape_forward <= s.wape_forward - wape_gain),
        "wape_reverse_lower_by_0.10": bool(c.wape_reverse <= s.wape_reverse - wape_gain),
    }
    return {"adopt": all(checks.values()), "checks": checks,
            "composite": {k: float(c[k]) for k in ("step_index", "bias_forward", "bias_reverse", "wape_forward", "wape_reverse")},
            "single": {k: float(s[k]) for k in ("step_index", "bias_forward", "bias_reverse", "wape_forward", "wape_reverse")}}


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

    def seg_pred(seg, a, b):
        """Estimate per segment: a_m M + b_m (prorated for partial segments)."""
        m = seg.month.to_numpy() - 1
        return a[m] * seg.M.to_numpy() + b[m] * (seg.ndays / seg.month_days).to_numpy()

    def h_mean(years, model):
        seg = rs[rs.year.isin(years)]
        est = np.where(seg.viirs_era, 0.0, model(seg))
        if callable(getattr(model, "scale_by_year", None)):
            est = model.scale_by_year(seg, est)
        return np.where(seg.viirs_era, seg.V, est).sum() / len(years)

    class Simple:
        def __init__(self, a, b):
            self.a, self.b = a, b

        def __call__(self, seg):
            return seg_pred(seg, self.a, self.b)

    class ShapeLevel:
        """Shape from (aS, bS), level from aL, scaled per year over the estimated segments."""
        def __init__(self, aS, bS, aL):
            self.aS, self.bS, self.aL = aS, bS, aL

        def __call__(self, seg):
            return seg_pred(seg, self.aS, self.bS)

        def scale_by_year(self, seg, est):
            mask = ~seg.viirs_era.to_numpy()
            level = seg_pred(seg, self.aL, np.zeros(12))
            out = est.copy()
            out[mask] = shape_level(est[mask], level[mask], seg.year.to_numpy()[mask])
            return out

        def table(self, den):
            return shape_level(self.aS * den + self.bS, self.aL * den)

    def evaluate(name, scale_g, fold_models, overlap_model, overlap_draws, k_info):
        """fold_models[fold] -> (test YearMonth, pred (ny,12)); overlap_model(point) and draws -> continuity."""
        rec = {"strategy": name, "scale": scale_g, **k_info}
        for fold, (lt, pred) in fold_models.items():
            rec[f"wape_{fold}"], rec[f"bias_{fold}"] = wape_bias(lt.num, pred)
            for i, y in enumerate(lt.years):
                by_year.append({"strategy": name, "fold": fold, "year": int(y), "obs": lt.num[i].sum(),
                                "pred": pred[i].sum()})
        idx = h_mean(after, overlap_model) / h_mean(before, overlap_model) / m_step
        draws = np.array([h_mean(after, d) / h_mean(before, d) / m_step for d in overlap_draws])
        o = rs[rs.year.isin(ov) & rs.viirs_era]
        pred = overlap_model(o)
        if callable(getattr(overlap_model, "scale_by_year", None)):
            pred = shape_level(pred, seg_pred(o, overlap_model.aL, np.zeros(12)), o.year.to_numpy())
        py = o.assign(pred=pred).groupby("year")[["pred", "V"]].sum()
        obs_pred = (py.V / py.pred).to_numpy()
        rng = np.random.default_rng(boot["seed"])          # same noise draws for every strategy
        noise = rng.choice(obs_pred, (len(draws), 3)).mean(1) / obs_pred.mean()
        old = np.nanquantile(draws, [0.05, 0.95])
        new = np.nanquantile(draws * noise, [0.05, 0.95])
        rec.update({"step_index": idx, "old_band": old, "new_band": new,
                    "flag_old": not old[0] <= 1 <= old[1], "flag_new": not new[0] <= 1 <= new[1],
                    "insample_pred_over_obs": float(py.pred.sum() / py.V.sum())})
        rows.append(rec)

    def fitted(strat, which):
        """Point fit (a, b, k) of a strategy on a table set ('fit', 'test', 'ov')."""
        g = strat.partition(":")[2] or None
        lf, dfit = tabs[which][0], tabs[which][1].get(g)
        k = choose_k(strat, lf, dfit, scale.get(g, 1), grid_k) if needs_k(strat) else None
        a, b = fit(strat, lf, dfit, k, scale.get(g, 1))
        return a[0], b[0], k

    def draws_of(strat, k):
        g = strat.partition(":")[2] or None
        return fit(strat, tabs["ov"][0], tabs["ov"][1].get(g), k, scale.get(g, 1), W)

    folds = {"forward": ("fit", "test"), "reverse": ("test", "fit")}
    rows, by_year = [], []
    for strat in strategies_for(cfg, region):
        g = strat.partition(":")[2] or None
        fm, ks = {}, {}
        for fold, (fa, ta) in folds.items():
            a, b, k = fitted(strat, fa)
            lt = tabs[ta][0]
            fm[fold] = (lt, a * lt.den + b)
            ks[f"k_{fold}"] = k
        a, b, k = fitted(strat, "ov")
        A, B = draws_of(strat, k)
        evaluate(strat, scale.get(g), fm, Simple(a, b), [Simple(A[i], B[i]) for i in range(len(W))],
                 {**ks, "k_overlap": k})

    def rank(df):
        # Ranking (continuity and bias first, WAPE second):
        #  1. continuity not flagged under the new band;
        #  2. score = |step index - 1| + mean(|forward bias|, |reverse bias|)  (both hold-out folds: one
        #     4-year fold alone is too noisy for Lebanon);
        #  3. forward WAPE.
        df = df.copy()
        df["bias_both"] = (df.bias_forward.abs() + df.bias_reverse.abs()) / 2
        df["score"] = (df.step_index - 1).abs() + df.bias_both
        return df.sort_values(["flag_new", "score", "wape_forward"]).reset_index(drop=True)

    res = rank(pd.DataFrame(rows))

    # affine_shape_single_level: monthly shape from the best-ranked affine model, annual level from single
    best_affine = res[res.strategy.str.startswith("affine")].strategy.iloc[0]
    fm, ks = {}, {}
    for fold, (fa, ta) in folds.items():
        aS, bS, k = fitted(best_affine, fa)
        aL, _, _ = fitted("single", fa)
        lt = tabs[ta][0]
        fm[fold] = (lt, ShapeLevel(aS, bS, aL).table(lt.den))
        ks[f"k_{fold}"] = k
    aS, bS, k = fitted(best_affine, "ov")
    aL, _, _ = fitted("single", "ov")
    AS, BS = draws_of(best_affine, k)
    AL, _ = draws_of("single", None)
    composite = "affine_shape_single_level"
    evaluate(composite, None, fm, ShapeLevel(aS, bS, aL), [ShapeLevel(AS[i], BS[i], AL[i]) for i in range(len(W))],
             {**ks, "k_overlap": k, "shape_strategy": best_affine})
    res = rank(pd.DataFrame(rows))
    decision = adoption(res, composite)
    decision["shape_strategy"] = best_affine
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
    write_report(cfg, region, res, by_year, zs, scale, n_local, excl, decision)
    print(decision)
    print(res[["strategy", "step_index", "flag_new", "bias_forward", "wape_forward"]].head(12).round(3).to_string())


def write_report(cfg, region, res, by_year, zs, scale, n_local, excl, decision):
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
    L += ["", "## affine_shape_single_level", "",
          f"Monthly shape from the best-ranked affine model (`{decision['shape_strategy']}`), each year scaled so "
          "its total (over estimated months) equals the single ratio's. Adopted as default only if continuity "
          "passes (new band), |bias| is no worse than single's on both folds, and WAPE is at least 0.10 lower "
          "on both folds.", "",
          "| check | result |", "|---|---|"]
    L += [f"| {k} | {'yes' if v else 'no'} |" for k, v in decision["checks"].items()]
    L += [f"| **adopt** | **{'yes' if decision['adopt'] else 'no'}** |", "",
          "| | step index | forward bias | reverse bias | forward WAPE | reverse WAPE |", "|---|---|---|---|---|---|"]
    for name in ("composite", "single"):
        d = decision[name]
        L.append(f"| {'affine_shape_single_level' if name == 'composite' else 'single'} | {d['step_index']:.3f} | "
                 f"{d['bias_forward']:+.1%} | {d['bias_reverse']:+.1%} | {d['wape_forward']:.3f} | {d['wape_reverse']:.3f} |")
    top = list(res.strategy.head(4)) + [s for s in ("local", "affine_shape_single_level", "blend:eastmed_pool")
                                        if s not in list(res.strategy.head(4))]
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
