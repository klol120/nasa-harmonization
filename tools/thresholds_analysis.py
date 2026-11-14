"""Thresholds from the subsampling experiment (tools/thresholds_experiment.py).

  N_month    n (local MODIS fire-days in a calendar month, overlap years) above which local monthly
             ratios beat the fixed-borrowing alternatives (single, donor, Lebanon strategy) for that
             month. Per-month error = sum |pred - obs| / sum obs over both hold-out folds (9 test
             years), pooled within log-spaced n bins (ratio of sums).
  N_country  share of thin months (n_m < N_month) at or above which the Lebanon strategy beats
             local for the region; also expressed as the annual MODIS total. Per-run score = mean of
             forward and reverse WAPE (region monthly totals).
  N_min      annual local MODIS fire-days below which the donor pool alone beats every strategy
             that uses local data (local, single, Lebanon strategy).

Ties go to the simpler choice: a challenger must win by more than DELTA (0.01 WAPE) to count, so
local keeps a month unless an alternative is better by DELTA, the Lebanon strategy must beat local by
DELTA, and the donor pool must beat every local-data strategy by DELTA. A sensitivity run uses 0.

Each crossing is read from a monotone (isotonic, count-weighted) fit of the challenger's advantage
across bins, so one noisy bin cannot move it: the threshold is the first bin edge where the fitted
advantage is <= DELTA (or, for the thin share, > DELTA). Confidence
ranges: 5-95 % over a cluster bootstrap of runs (resampled within region x fraction), 1000 draws.

Run: .venv/bin/python tools/thresholds_analysis.py
Writes docs/reports/thresholds_data/thresholds.json (and, from step 3, the chart and report).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs/reports/thresholds_data"
REGIONS = ["greece", "eastmed"]
S = ["local", "single", "blend", "donor", "lebanon"]
FIXED_ALT = ["single", "donor", "lebanon"]          # alternatives that borrow by construction
N_BOOT, SEED = 1000, 20261114
DELTA = 0.01
MONTH_BINS = [0, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90, 110, 130, 150, 175, 200, 250, 300, 400, 500,
              700, 1000, np.inf]
ANNUAL_BINS = [0, 2, 3, 5, 7, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90, 110, 130, 150, 200, 250, 350, 500, 750,
               1000, 2500, np.inf]
THIN_BINS = [i / 12 - 1e-9 for i in range(13)] + [np.inf]


def load(region):
    m = pd.read_csv(DATA / f"{region}_months.csv.gz")
    runs = pd.read_csv(DATA / f"{region}_runs.csv.gz")
    for s in S:
        w = runs[[f"{s}_wape_forward", f"{s}_wape_reverse"]]
        runs[f"{s}_unusable"] = w.isna().any(axis=1)
        runs[f"{s}_score"] = w.fillna(1.0).mean(axis=1)      # undefined fit (no local MODIS) = predicting nothing
    runs["run"] = region + ":" + runs.frac.astype(str) + ":" + runs.rep.astype(str)
    m["run"] = region + ":" + m.frac.astype(str) + ":" + m.rep.astype(str)
    a = m.pivot_table(index=["run", "month"], columns="strategy", values="abs_err", aggfunc="sum")
    o = m[m.strategy == "local"].groupby(["run", "month"]).obs.sum().rename("obs")
    n = runs.melt(id_vars=["run"], value_vars=[f"n_m{i}" for i in range(1, 13)], var_name="month", value_name="n")
    n["month"] = n.month.str[3:].astype(int)
    pm = a.join(o).reset_index().merge(n, on=["run", "month"])
    for s in S:                                               # undefined -> error = obs (predicting nothing)
        pm[s] = pm[s].fillna(pm.obs)
    pm["region"], runs["region"] = region, region
    return pm, runs


def binned_ratio(pm, bins):
    """Per n-bin ratio-of-sums error for each strategy."""
    b = pd.cut(pm.n, bins, right=False)
    g = pm.groupby(b, observed=False)
    out = pd.DataFrame({s: g[s].sum() / g.obs.sum() for s in S})
    out["count"] = g.size()
    out["lo"] = [i.left for i in out.index]
    out["hi"] = [i.right for i in out.index]
    return out.reset_index(drop=True)


def binned_mean(runs, x, bins, cols):
    b = pd.cut(runs[x], bins, right=False)
    g = runs.groupby(b, observed=False)
    out = pd.DataFrame({c: g[c].mean() for c in cols})
    out["count"] = g.size()
    out["lo"] = [i.left for i in out.index]
    out["hi"] = [i.right for i in out.index]
    return out.reset_index(drop=True)


def centre(lo, hi, log):
    """Bin position: geometric centre on a log axis (n); for thin shares the bin holds one value, k/12."""
    if not log:
        return np.round(lo * 12) / 12
    hi = np.where(np.isfinite(hi), hi, lo * 2)
    return np.where(lo > 0, np.sqrt(np.maximum(lo, 1e-9) * hi), hi / 2)


def isotonic_decreasing(y, w):
    """Weighted least-squares non-increasing fit (pool-adjacent-violators)."""
    blocks = []                                  # [mean, weight, count]
    for v, wt in zip(y, w):
        blocks.append([v, wt, 1])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            m2, w2, c2 = blocks.pop()
            m1, w1, c1 = blocks.pop()
            blocks.append([(m1 * w1 + m2 * w2) / (w1 + w2), w1 + w2, c1 + c2])
    return np.concatenate([[m] * c for m, _, c in blocks])


def crossing(tab, gap, delta, min_count=20, increasing=False):
    """First bin edge where the monotone fit of `gap` (a Series aligned with tab) is <= delta.

    The gap is the advantage of the challenger (positive = challenger better). With more data it is
    assumed to shrink (non-increasing in the bin variable; `increasing=True` for the thin-month share,
    where the challenger's advantage grows). Returns nan if the fit never reaches delta, and the first
    populated edge if it is already there."""
    m = (tab["count"] >= min_count).to_numpy() & np.isfinite(gap.to_numpy())
    x = centre(tab.lo.to_numpy()[m], tab.hi.to_numpy()[m], log=not increasing)
    g, w = gap.to_numpy()[m], tab["count"].to_numpy()[m].astype(float)
    if not len(g):
        return np.nan
    fit = isotonic_decreasing(g[::-1], w[::-1])[::-1] if increasing else isotonic_decreasing(g, w)
    # crossing of the fitted advantage through delta, interpolated between bin centres (log n for counts)
    hit = np.nonzero(fit > delta)[0] if increasing else np.nonzero(fit <= delta)[0]
    if not len(hit):
        return np.nan
    i = hit[0]
    if i == 0:
        return float(x[0])
    f0, f1 = fit[i - 1], fit[i]
    s = (delta - f0) / (f1 - f0) if f1 != f0 else 1.0
    if increasing:
        return float(x[i - 1] + s * (x[i] - x[i - 1]))
    return float(np.exp(np.log(x[i - 1]) + s * (np.log(x[i]) - np.log(x[i - 1]))))


def thresholds(pm, runs, delta=DELTA):
    tab_m = binned_ratio(pm, MONTH_BINS)
    # challenger = best fixed alternative; its advantage over local shrinks with n
    n_month = crossing(tab_m, tab_m.local - tab_m[FIXED_ALT].min(axis=1), delta)
    runs = runs.copy()
    nm = runs[[f"n_m{i}" for i in range(1, 13)]].to_numpy()
    thr = n_month if np.isfinite(n_month) else np.inf
    runs["thin_share"] = (nm < thr).mean(1)
    tab_t = binned_mean(runs, "thin_share", THIN_BINS, [f"{s}_score" for s in S])
    # N_country: Lebanon strategy better than local at thin share >= N_country
    # Lebanon strategy's advantage over local grows with the thin share: first share where it exceeds delta
    n_country = crossing(tab_t, tab_t.local_score - tab_t.lebanon_score, delta, increasing=True)
    tab_a = binned_mean(runs, "n_annual", ANNUAL_BINS, [f"{s}_score" for s in S] + [f"{s}_cont_pass" for s in S]
                        + [f"{s}_unusable" for s in S])
    # the same comparison on the annual total: local better than Lebanon strategy above
    # ... and shrinks with the annual total: local is the choice from N_country_annual up
    n_country_annual = crossing(tab_a, tab_a.local_score - tab_a.lebanon_score, delta)
    # donor-only's advantage over every local-data strategy shrinks with n: below N_min it exceeds delta
    best_local = tab_a[["local_score", "single_score", "lebanon_score"]].min(axis=1)
    n_min = crossing(tab_a, best_local - tab_a.donor_score, delta)
    return {"N_month": n_month, "N_country": n_country, "N_country_annual": n_country_annual, "N_min_annual": n_min}, \
        {"month": tab_m, "thin": tab_t, "annual": tab_a}


def bootstrap(pm, runs):
    rng = np.random.default_rng(SEED)
    runs = runs.reset_index(drop=True)
    groups = [g.index.to_numpy() for _, g in runs.groupby(["region", "frac"])]
    rows_of = pm.groupby("run").indices                       # run -> row positions in pm
    draws = []
    for _ in range(N_BOOT):
        pick = np.concatenate([rng.choice(g, len(g)) for g in groups])
        r = runs.iloc[pick].reset_index(drop=True)
        p = pm.iloc[np.concatenate([rows_of[x] for x in r.run])].reset_index(drop=True)
        draws.append(thresholds(p, r)[0])
    return pd.DataFrame(draws)


def k_vs_n(runs):
    """Blend k chosen on the fit years (forward fold), by annual n."""
    b = pd.cut(runs.n_annual, ANNUAL_BINS, right=False)
    g = runs.groupby(b, observed=True).blend_k_forward
    return pd.DataFrame({"median_k": g.median(), "share_k_le_20": g.apply(lambda k: (k <= 20).mean()), "count": g.size()})


def main():
    loaded = {r: load(r) for r in REGIONS}
    result = {}
    for label, regions in [("greece", ["greece"]), ("eastmed", ["eastmed"]), ("pooled", REGIONS)]:
        pm = pd.concat([loaded[r][0] for r in regions], ignore_index=True)
        runs = pd.concat([loaded[r][1] for r in regions], ignore_index=True)
        point, tabs = thresholds(pm, runs)
        bs = bootstrap(pm, runs)
        result[label] = {
            "point": point,
            "point_delta0": thresholds(pm, runs, 0.0)[0],
            "ci90": {k: [float(np.nanquantile(bs[k], 0.05)), float(np.nanquantile(bs[k], 0.95))] for k in point},
            "boot_nan_share": {k: float(bs[k].isna().mean()) for k in point},
            "tables": {k: v.replace([np.inf, -np.inf], None).to_dict(orient="records") for k, v in tabs.items()},
            "k_vs_n": k_vs_n(runs).reset_index().astype({"n_annual": str}).to_dict(orient="records"),
            "runs": int(len(runs)),
        }
        print(label, point, result[label]["ci90"])
    (DATA / "thresholds.json").write_text(json.dumps(result, indent=1, default=float))


if __name__ == "__main__":
    main()
