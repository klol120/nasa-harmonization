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
    chart(result)
    report(result)


# ---------------------------------------------------------------- step 3: chart and report

ADOPT_FROM = "pooled"          # thresholds written to config: both regions' evidence (see report)
INK, INK2, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
COLOR = {"local": "#2a78d6", "single": "#eb6834", "blend": "#1baf7a", "donor": "#eda100", "lebanon": "#e87ba4"}
MARKER = {"local": "o", "single": "s", "blend": "^", "donor": "D", "lebanon": "v"}
LABEL = {"local": "local monthly ratios", "single": "single ratio", "blend": "blend (k by LOYO)",
         "donor": "donor pool only", "lebanon": "Lebanon strategy (single level + pooled affine shape)"}


def adopted(result):
    p = result[ADOPT_FROM]["point"]
    return {"N_month": round(p["N_month"]), "N_country": round(p["N_country"], 2),
            "N_country_annual": round(p["N_country_annual"]), "N_min_annual": round(p["N_min_annual"], 1)}


def chart(result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "axes.edgecolor": BASE, "axes.labelcolor": INK2, "xtick.color": MUTED,
                         "ytick.color": MUTED, "text.color": INK, "axes.titlecolor": INK, "figure.facecolor": SURFACE,
                         "axes.facecolor": SURFACE})
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.6), constrained_layout=True)
    ad = adopted(result)
    panels = [("month", "N_month", True, "local MODIS fire-days in the calendar month, 2012–2020 (n)",
               "error per calendar month\n(Σ|pred − obs| / Σ obs, both folds)", None),
              ("thin", "N_country", False, "share of thin months (n < N_month of that region)",
               "region hold-out WAPE\n(mean of both folds)", "_score"),
              ("annual", "N_country_annual", True, "local MODIS fire-days per year (2012–2020 mean)",
               "region hold-out WAPE\n(mean of both folds)", "_score")]
    for r, region in enumerate(REGIONS):
        res = result[region]
        for c, (tab, key, logx, xlabel, ylabel, sfx) in enumerate(panels):
            ax = axes[r, c]
            d = pd.DataFrame(res["tables"][tab])
            d = d[d["count"] >= 20]
            x = centre(d.lo.to_numpy(float), d.hi.astype(float).fillna(np.inf).to_numpy(), log=logx)
            for s in S:
                y = d[s + (sfx or "")].to_numpy()
                ax.plot(x, y, color=COLOR[s], lw=2, marker=MARKER[s], ms=5, mec=SURFACE, mew=1, zorder=3)
            marks = [(key, res["point"][key], res["ci90"][key], f"{region}")]
            if c == 2:
                marks.append(("N_min_annual", res["point"]["N_min_annual"], res["ci90"]["N_min_annual"], "N_min"))
            for k, v, ci, name in marks:
                if v is None or not np.isfinite(v):
                    continue
                ax.axvspan(ci[0], ci[1], color=INK, alpha=0.07, lw=0, zorder=1)
                ax.axvline(v, color=INK, lw=1.2, ls="-", zorder=2)
                txt = (f"{k.replace('_annual', '')} = {v:.2f}" if k == "N_country" else f"{k.replace('_annual', '')} = {v:.0f}" if v >= 10 else f"{k.replace('_annual', '')} = {v:.1f}")
                ax.annotate(f"{txt}\n90%: {ci[0]:.3g}–{ci[1]:.3g}", (v, 1), xycoords=("data", "axes fraction"),
                            xytext=(4, -4), textcoords="offset points", va="top", fontsize=8, color=INK, zorder=5,
                            bbox={"boxstyle": "round,pad=0.25", "fc": SURFACE, "ec": GRID, "lw": 0.6})
            akey = key if key != "N_country_annual" else "N_country_annual"
            ax.axvline(ad[akey], color=INK2, lw=1, ls=(0, (4, 3)), zorder=2)
            if c == 2:
                ax.axvline(ad["N_min_annual"], color=INK2, lw=1, ls=(0, (4, 3)), zorder=2)
            if logx:
                ax.set_xscale("log")
            ax.grid(True, color=GRID, lw=0.6)
            ax.set_axisbelow(True)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.set_ylim(0, None)
            ax.set_xlabel(xlabel)
            if c == 0:
                ax.set_ylabel(ylabel)
            ax.set_title(f"{region.capitalize()} subsamples · " + {"month": "N_month", "thin": "N_country (thin share)",
                                                                   "annual": "N_country (annual) and N_min"}[tab],
                         loc="left", fontsize=10)
    handles = [plt.Line2D([], [], color=COLOR[s], marker=MARKER[s], lw=2, ms=5, label=LABEL[s]) for s in S]
    handles += [plt.Line2D([], [], color=INK, lw=1.2, label="threshold for this region (shaded: 90% range)"),
                plt.Line2D([], [], color=INK2, lw=1, ls=(0, (4, 3)), label=f"adopted ({ADOPT_FROM}, config.yaml)")]
    fig.legend(handles=handles, loc="outside upper center", ncol=4, frameon=False, fontsize=9)
    fig.savefig(ROOT / "docs/reports/thresholds.png", dpi=150)


def region_months():
    """n per calendar month (local MODIS fire-days, overlap years, fitting inputs) for the real regions."""
    from firecal.config import load_config
    from firecal.fitting import FitSpec, table

    cfg = load_config()
    y0, y1 = cfg["calibration"]["overlap_years"]
    excl = cfg["persistence"]["exclude_from_calibration"]
    return {r: table(cfg, r, FitSpec("a", list(range(y0, y1 + 1)), excl)).den.sum(0) for r in ("lebanon", "greece", "eastmed")}


def rule(n_m, thr, years=9):
    annual = n_m.sum() / years
    thin = n_m < thr["N_month"]
    if annual < thr["N_min_annual"]:
        pick = "donor"
    elif thin.mean() >= thr["N_country"]:
        pick = "lebanon"
    else:
        pick = "local"
    return pick, thin, annual


def v1_picks(tag="v1.0-data"):
    """Strategies of the frozen release, in the rule's vocabulary (read from the tag's config.yaml)."""
    import subprocess

    import yaml

    cfg = yaml.safe_load(subprocess.run(["git", "show", f"{tag}:config.yaml"], cwd=ROOT, capture_output=True,
                                        text=True, check=True).stdout)
    names = {"local": "local", "affine_shape_single_level_pool": "lebanon"}
    return {r: names.get(s, s) for r, s in cfg["calibration"]["strategy"].items()}


def report(result):
    ad = adopted(result)
    months = region_months()
    v1 = v1_picks()
    fmt = lambda k, v: "—" if v is None or not np.isfinite(v) else (f"{v:.2f}" if k == "N_country" else f"{v:.0f}" if v >= 10 else f"{v:.1f}")  # noqa: E731
    keys = ["N_month", "N_country", "N_country_annual", "N_min_annual"]
    L = ["# Data-thinness thresholds (derived, 2026-11-14)", "",
         "Derived from a cell-subsampling experiment instead of being hand-set. Code: "
         "`tools/thresholds_experiment.py` (runs) and `tools/thresholds_analysis.py` (thresholds, this report, "
         "`thresholds.png`). Raw results: `docs/reports/thresholds_data/`.", "",
         "![error vs n](thresholds.png)", "",
         "## Experiment", "",
         "- Greece and EastMed. Each run keeps 100, 50, 20, 10, 5 and 2 % of the region's cells (plus 1 and 0.5 % "
         "to locate N_min), with 200 repetitions per fraction. Seed 20261114; each run's seed is recorded.",
         "- Five strategies are fitted per run: local monthly ratios; single ratio; blend (k by leave-one-year-out on "
         "the fit years); donor pool only; and the Lebanon strategy (annual level from single, monthly shape from "
         "the affine blend with the donor pool).",
         "- Donors are disjoint from the subsampled region: `eastmed_pool` for Greece (Lebanon's pool), and all "
         "of Greece for EastMed.",
         "- Fitting inputs are the pipeline's: usable dates only, persistent fire-days excluded.",
         "- Each run is scored on the forward (fit 2012–16, test 2017–20) and reverse hold-out folds, on region "
         "monthly totals, and on the 2012 continuity check (step index and band, as in validate).",
         "- At 100 % the harness reproduces validate's Greece hold-out exactly (local 0.188/0.152, single "
         "0.265/0.221, blend 0.186/0.147, Lebanon strategy 0.315/0.158).", "",
         "## Definitions", "",
         "- **n** = local MODIS fire-days in a calendar month, summed over 2012–2020. The annual total is "
         "Σn / 9.",
         "- **N_month:** n above which local monthly ratios are no worse (within 0.01) than the best fixed-borrowing "
         "alternative (single, donor, Lebanon strategy) for that month. Blend contains local and converges to it, "
         "so it is reported separately.",
         "- **N_country:** the share of thin months (n < N_month) at or above which the Lebanon strategy beats "
         "local by more than 0.01 WAPE. It is also given as an annual total.",
         "- **N_min:** the annual total below which the donor pool alone beats every strategy that uses local "
         "data by more than 0.01.",
         "- **Estimation:** each crossing is read from a monotone (isotonic, count-weighted) fit of the "
         "challenger's advantage across bins, interpolated between bin centres. Ties go to the simpler choice. "
         "The 90 % range comes from a 1,000-draw cluster bootstrap of runs within region × fraction.", "",
         "## Results", "",
         "| threshold | Greece | EastMed | pooled | δ = 0 (Greece / EastMed / pooled) | **adopted** |",
         "|---|---|---|---|---|---|"]
    for k in keys:
        cells = []
        for lab in ("greece", "eastmed", "pooled"):
            v, ci = result[lab]["point"][k], result[lab]["ci90"][k]
            cells.append(f"{fmt(k, v)} [{fmt(k, ci[0])}–{fmt(k, ci[1])}]")
        d0 = " / ".join(fmt(k, result[lab]["point_delta0"][k]) for lab in ("greece", "eastmed", "pooled"))
        L.append(f"| {k} | " + " | ".join(cells) + f" | {d0} | **{fmt(k, ad[k])}** |")
    L += ["",
          f"**Adopted: the pooled estimates** (`{ADOPT_FROM}`), so both regions' evidence counts. The bootstrap "
          "ranges are narrow because 200 repetitions pin each region's curve down. **The real uncertainty is "
          "between regions:**",
          "- **N_month: 61 in Greece, 426 in EastMed.** In EastMed the Lebanon strategy's affine shape beats local "
          "ratios up to about n = 400, because much of EastMed's activity is VIIRS fire in cell-days that MODIS "
          "doesn't see. That's a model-form effect as well as thinness.",
          "- **EastMed is sensitive to the tie rule** (δ = 0 moves its N_month to about 780). Greece is not.",
          "",
          "## Check against Lebanon (Dec–May thin, Jun–Nov enough) and k = 20", "",
          "| month | " + " | ".join(MONTHS_ABBR) + " |", "|---|" + "---|" * 12,
          "| Lebanon n | " + " | ".join(f"{x:.0f}" for x in months["lebanon"]) + " |"]
    for lab in ("greece", "pooled"):
        thr = result[lab]["point"]["N_month"]
        L.append(f"| thin at N_month = {thr:.0f} ({lab}) | " + " | ".join("thin" if x < thr else "" for x in months["lebanon"]) + " |")
    L += ["",
          "- **Dec–May thin: confirmed** at every threshold (n = 2–10, far below any range).",
          "- **Jun–Nov enough: not confirmed.**",
          "  - Greece's N_month (61) also makes Jun (27), Jul (56) and Nov (53) thin, leaving only Aug–Oct rich.",
          "  - The pooled N_month (149) makes every Lebanon month thin, since Lebanon's largest month is Oct with "
          "133.",
          "  - The earlier Jun–Nov reading was optimistic: in subsamples, a month with Lebanon's Jun–Nov n is "
          "predicted better by borrowing.",
          "- **k = 20:**",
          "  - Blend weight on local is w = n / (n + k). With k = 20, w is 0.75 at Greece's N_month (61) and 0.88 "
          "at the pooled 149, so local dominates by the time the thresholds say it should.",
          "  - The k chosen by leave-one-year-out in the subsamples centres on 10–50 for regions of Lebanon's "
          "size (annual 20–110), with k ≤ 20 in 35–65 % of runs. It falls to 5 or 0 as n grows.",
          "  - Blend's advantage over local drops below 0.01 at n ≈ 175 in Greece and ≈ 60 in EastMed. **k = 20 "
          "is consistent with the data.**", "",
          "## Rule (for add-country) and regression against v1.0-data", "",
          "Rule: annual < N_min → `donor`; else thin share ≥ N_country → Lebanon strategy; else `local`.", "",
          "v1.0-data strategies are read from the tag's config.yaml.", "",
          "| region | annual n | thin months (adopted N_month) | thin share | rule picks | v1.0-data | same? |",
          "|---|---|---|---|---|---|---|"]
    for r, n_m in months.items():
        pick, thin, annual = rule(n_m, ad)
        tm = ", ".join(MONTHS_ABBR[i] for i in range(12) if thin[i]) or "none"
        L.append(f"| {r} | {annual:.1f} | {tm} | {thin.mean():.2f} | {pick} | {v1[r]} | {'yes' if pick == v1[r] else '**no**'} |")
    for lab in ("greece", "eastmed"):
        thr = {k: result[lab]["point"][k] for k in keys}
        picks = {r: rule(n_m, thr)[0] for r, n_m in months.items()}
        L.append("")
        L.append(f"With {lab}-only thresholds the picks are: " + ", ".join(f"{r} {p}" for r, p in picks.items())
                 + (" (all as v1.0-data)." if all(picks[r] == v1[r] for r in picks) else " (**differs from v1.0-data**)."))
    L += ["", "## Binned results (pooled)", "",
          "Error per calendar month by n (ratio of sums over both folds):", "",
          "| n from | runs×months | " + " | ".join(S) + " |", "|---|---|" + "---|" * len(S)]
    for x in result["pooled"]["tables"]["month"]:
        if x["count"] >= 20:
            L.append(f"| {x['lo']:g} | {x['count']} | " + " | ".join(f"{x[s]:.3f}" for s in S) + " |")
    L += ["", "Region hold-out WAPE (mean of both folds) and continuity pass rate, by annual n:", "",
          "| annual n from | runs | " + " | ".join(S) + " | continuity pass (local / Lebanon / donor) |",
          "|---|---|" + "---|" * len(S) + "---|"]
    for x in result["pooled"]["tables"]["annual"]:
        if x["count"] >= 20:
            L.append(f"| {x['lo']:g} | {x['count']} | " + " | ".join(f"{x[s + '_score']:.3f}" for s in S)
                     + f" | {x['local_cont_pass']:.0%} / {x['lebanon_cont_pass']:.0%} / {x['donor_cont_pass']:.0%} |")
    (ROOT / "docs/reports/thresholds.md").write_text("\n".join(L) + "\n")


MONTHS_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


if __name__ == "__main__":
    main()
