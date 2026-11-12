"""Validation (method section 5): hold-out per strategy, counting-unit table, continuity at 2012,
breaks at MODIS processing changes. Writes holdout/breaks tables and docs/reports/{region}_validation.md.

Two variants are scored: `pdf_rules` (no persistence exclusion, comparable with the PDF tables) and,
when persistence.exclude_from_calibration is on, `persistence_excluded`.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..calibration import choose_k, factors, predict, wape_bias
from ..config import as_date, path
from ..firedays import count_by_sensor
from ..fitting import FitSpec, chosen, donor_groups, expand_strategies, fit_all, table
from ..geo import cell_index
from ..io import read_report, read_stage, write_stage

log = logging.getLogger(__name__)


def variants(cfg) -> list[tuple[str, bool]]:
    v = [("pdf_rules", False)]
    if cfg["persistence"]["exclude_from_calibration"]:
        v.append(("persistence_excluded", True))
    return v


def holdout(cfg: dict, region: str) -> pd.DataFrame:
    h = cfg["calibration"]["holdout"]
    fit, test = list(range(h["fit"][0], h["fit"][1] + 1)), list(range(h["test"][0], h["test"][1] + 1))
    groups = donor_groups(cfg, region)
    strategies = expand_strategies(cfg, region, cfg["calibration"]["strategies"])
    rows = []
    for name, excl in variants(cfg):
        for fold, (fy, ty) in {"forward": (fit, test), "reverse": (test, fit)}.items():
            lf, lt = table(cfg, region, FitSpec("a", fy, excl)), table(cfg, region, FitSpec("a", ty, excl))
            donors = {}
            for strat in strategies:
                kind, _, g = strat.partition(":")
                donor, k = None, None
                if g:
                    donors.setdefault(g, table(cfg, groups[g]["region"], FitSpec("a", fy, excl), groups[g]["countries"]))
                    donor = donors[g]
                if kind == "blend":
                    k, _ = choose_k(lf, donor, cfg["calibration"]["blend_k_grid"])   # chosen on fit years only
                a = factors(strat, lf.sums(), donor.sums() if donor else None, k)["a"][0]
                wape, bias = wape_bias(lt.num, predict(a, lt.den))
                rows.append({"variant": name, "fold": fold, "fit": f"{fy[0]}-{fy[-1]}", "test": f"{ty[0]}-{ty[-1]}",
                             "strategy": strat, "k": k, "wape": wape, "bias": bias,
                             "test_viirs": float(lt.num.sum()), "test_modis": float(lt.den.sum())})
    return pd.DataFrame(rows)


def counting_units(cfg: dict, region: str) -> pd.DataFrame:
    """PDF Table 1: VIIRS/MODIS ratio by counting unit on the overlap years."""
    y0, y1 = cfg["calibration"]["overlap_years"]
    det = read_stage(cfg, region, "detections_clean")
    det = det[det.datetime_utc.dt.year.between(y0, y1)]
    stats = read_stage(cfg, region, "persistent_sources")
    row, col = cell_index(det.lat, det.lon, cfg["persistence"]["cell_deg"])
    pcell = pd.Series(row).astype(str).values + "_" + pd.Series(col).astype(str).values
    persistent = np.isin(pcell, stats.pcell[stats.flagged].values)
    rows = []
    for name, excl in variants(cfg):
        d = det[~persistent] if excl else det
        n = d.sensor.value_counts()
        rows.append({"variant": name, "unit": "detections", "viirs": int(n["VIIRS"]), "modis": int(n["MODIS"]),
                     "ratio": n["VIIRS"] / n["MODIS"]})
        for g in (0.01, 0.05, 0.10):
            c = count_by_sensor(d, g)
            rows.append({"variant": name, "unit": f"fire-days {g:.2f}°", "viirs": int(c["VIIRS"]),
                         "modis": int(c["MODIS"]), "ratio": c["VIIRS"] / c["MODIS"]})
    return pd.DataFrame(rows)


def log_correlation(cfg: dict, region: str) -> dict:
    y0, y1 = cfg["calibration"]["overlap_years"]
    out = {}
    for name, excl in variants(cfg):
        t = table(cfg, region, FitSpec("a", list(range(y0, y1 + 1)), excl))
        m = (t.num > 0) & (t.den > 0)
        out[name] = {"r": float(np.corrcoef(np.log(t.num[m]), np.log(t.den[m]))[0, 1]), "months": int(m.sum()),
                     "months_total": int(m.size)}
    return out


def region_segments(cfg: dict, region: str) -> pd.DataFrame:
    """Region totals per segment (all data) joined to the segment calendar."""
    fs = read_stage(cfg, region, "fire_segments")
    seg = read_stage(cfg, region, "segments")
    cols = [c for c in fs.columns if c.startswith("n_")]
    tot = fs.groupby(["year", "month", "seg"])[cols].sum().reset_index()
    return seg.merge(tot, on=["year", "month", "seg"], how="left").fillna({c: 0 for c in cols})


def continuity(cfg: dict, region: str, exclude_persistent: bool) -> dict:
    """Step at the splice, relative to MODIS: (H_after / H_before) / (M_after / M_before).

    About 1 when the harmonized series carries no artificial step. Factors are refitted on the overlap
    with the variant's persistence rule, and the region sums use matching columns, so like is compared
    with like. The band combines the a_m year bootstrap with the year-to-year spread of observed /
    predicted VIIRS on the overlap (each draw is multiplied by the mean of 3 resampled overlap years),
    because a perfect calibration still varies from year to year.
    """
    pick = chosen(cfg, "calibration", region)
    y0, y1 = cfg["calibration"]["overlap_years"]
    fac, draws_long, _ = fit_all(cfg, region, FitSpec("a", list(range(y0, y1 + 1)), exclude_persistent), [pick])
    a, b = fac.set_index("month").a, fac.set_index("month").b
    boot = draws_long.pivot(index="draw", columns="month", values="a")
    boot_b = draws_long.pivot(index="draw", columns="month", values="b")
    sfx = "_np" if exclude_persistent else ""
    rs = region_segments(cfg, region).rename(columns={f"n_modis{sfx}": "M", f"n_viirs{sfx}": "V"})
    before, after = [2009, 2010, 2011], [2012, 2013, 2014]

    def h_total(years, a_by_month, b_by_month=None):
        s = rs[rs.year.isin(years)]
        est = s.M * s.month.map(a_by_month).to_numpy()
        if b_by_month is not None:   # affine intercept, prorated for partial segments
            est = est + s.month.map(b_by_month).to_numpy() * s.ndays / s.month_days
        return np.where(s.viirs_era, s.V, est).sum() / len(years)

    m_b = rs[rs.year.isin(before)].M.sum() / 3
    m_a = rs[rs.year.isin(after)].M.sum() / 3
    idx = (h_total(after, a, b) / h_total(before, a, b)) / (m_a / m_b)
    ov = rs[rs.year.between(y0, y1) & rs.viirs_era]
    per_year = ov.assign(pred=ov.M * ov.month.map(a) + ov.month.map(b) * ov.ndays / ov.month_days) \
        .groupby("year")[["pred", "V"]].sum()
    obs_over_pred = (per_year.V / per_year.pred).to_numpy()
    rng = np.random.default_rng(cfg["calibration"]["bootstrap"]["seed"])
    draws = np.array([(h_total(after, boot.loc[d], boot_b.loc[d]) / h_total(before, boot.loc[d], boot_b.loc[d]))
                      / (m_a / m_b) for d in boot.index])
    noise = rng.choice(obs_over_pred, (len(draws), 3)).mean(1) / obs_over_pred.mean()
    lo, hi = np.nanquantile(draws * noise, [0.05, 0.95])
    olo, ohi = np.nanquantile(draws, [0.05, 0.95])     # old band: factor bootstrap only
    return {"strategy": pick, "exclude_persistent": exclude_persistent, "before": before, "after": after,
            "step_index": float(idx), "band": [float(lo), float(hi)], "step_flagged": bool(not lo <= 1 <= hi),
            "band_factor_only": [float(olo), float(ohi)], "step_flagged_factor_only": bool(not olo <= 1 <= ohi),
            "modis_step": float(m_a / m_b), "harmonized_step": float(h_total(after, a, b) / h_total(before, a, b)),
            "overlap_pred_over_obs": (per_year.pred / per_year.V).round(3).to_dict()}


def breaks(cfg: dict, region: str) -> tuple[pd.DataFrame, list[dict]]:
    """Annual VIIRS/MODIS fire-day ratio with MODIS version; compares periods split at 2018 and 2023."""
    rs = region_segments(cfg, region)
    last = cfg["years"]["stats_last_year"]
    full = rs[rs.viirs_era & rs.year.between(as_date(cfg["sensors"]["viirs_start"]).year, last)]
    ann = full.groupby("year")[["n_viirs", "n_modis"]].sum()
    ann["ratio"] = ann.n_viirs / ann.n_modis
    det = read_stage(cfg, region, "detections_clean")
    det = det[det.sensor == "MODIS"]
    ver = det.groupby(det.datetime_utc.dt.year).version.agg(lambda v: ", ".join(sorted(v.dropna().unique())))
    ann["modis_version"] = ver.reindex(ann.index).fillna("")
    ann = ann.reset_index()
    periods = [(2012, 2017), (2018, 2022), (2023, last)]
    out = []
    base = ann[ann.year.between(*periods[0])].ratio
    for p0, p1 in periods:
        r = ann[ann.year.between(p0, p1)].ratio
        if len(r) < 2 or len(base) < 2:      # period outside the data (e.g. stats_last_year < 2023)
            continue
        t = (r.mean() - base.mean()) / np.sqrt(r.var(ddof=1) / len(r) + base.var(ddof=1) / len(base)) if p0 != 2012 else 0.0
        out.append({"period": f"{p0}-{p1}", "mean_ratio": float(r.mean()), "change_vs_2012_2017": float(r.mean() / base.mean() - 1),
                    "welch_t": float(t), "flagged": bool(abs(t) > 2)})
    return ann, out


def write_report(cfg, region, ho, cu, rlog, cont, ann, per, k_sel) -> None:
    out = path(cfg, "reports") / f"{region}_validation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    h = cfg["calibration"]["holdout"]
    L = [f"# {region}: validation", "",
         f"Strategy used downstream: `{chosen(cfg, 'calibration', region)}`. Overlap {cfg['calibration']['overlap_years']}.", "",
         "## Ratio by counting unit (PDF Table 1)", "", "| variant | unit | VIIRS | MODIS | VIIRS/MODIS |", "|---|---|---|---|---|"]
    L += [f"| {r.variant} | {r.unit} | {r.viirs} | {r.modis} | {r.ratio:.2f} |" for r in cu.itertuples()]
    L += ["", f"## Hold-out error of monthly totals (PDF Table 2): fit {h['fit'][0]}-{h['fit'][1]}, test {h['test'][0]}-{h['test'][1]}",
          "", "WAPE = Σ|N_V − Ñ_V| / Σ N_V, bias = Σ(Ñ_V − N_V) / Σ N_V. Reverse fold = fit on the test years, test on the fit years. "
          "Blend k is chosen by leave-one-year-out on the fit years only.", "",
          "| variant | strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |", "|---|---|---|---|---|---|---|"]
    f = ho[ho.fold == "forward"].set_index(["variant", "strategy"])
    r = ho[ho.fold == "reverse"].set_index(["variant", "strategy"])
    for (v, s), x in f.sort_values(["wape"]).sort_index(level=0, sort_remaining=False).iterrows():
        y = r.loc[(v, s)]
        k = "" if pd.isna(x.k) else f"{x.k:g}"
        L.append(f"| {v} | {s} | {k} | {x.wape:.3f} | {x.bias:+.1%} | {y.wape:.3f} | {y.bias:+.1%} |")
    L += ["", "## Monthly log-count correlation (overlap)", ""]
    L += [f"- {v}: r = {x['r']:.3f} over {x['months']} of {x['months_total']} months with both counts > 0" for v, x in rlog.items()]
    if len(k_sel):
        L += ["", "## Blend k selection on the full overlap (leave-one-year-out WAPE)", "",
              "| k | " + " | ".join(sorted(k_sel.strategy.unique())) + " |", "|---|" + "---|" * k_sel.strategy.nunique()]
        p = k_sel.pivot(index="k", columns="strategy", values="wape_loyo")
        L += [f"| {k:g} | " + " | ".join(f"{v:.3f}" for v in row) + " |" for k, row in p.iterrows()]
    L += ["", "## Continuity at 2012", "",
          "Step index = (H after / H before) / (MODIS after / MODIS before), before 2009-2011, after 2012-2014. "
          "About 1 means no artificial step. The 90% band combines the a_m bootstrap with year-to-year variation.", "",
          "| variant | step index | 90% band (with year spread) | result | old band (factor bootstrap only) | old result | harmonized step | MODIS step |",
          "|---|---|---|---|---|---|---|---|"]
    for v, c in cont.items():
        fo = c["band_factor_only"]
        L.append(f"| {v} | {c['step_index']:.3f} | [{c['band'][0]:.3f}, {c['band'][1]:.3f}] | "
                 f"{'**step flagged**' if c['step_flagged'] else 'no step'} | [{fo[0]:.3f}, {fo[1]:.3f}] | "
                 f"{'**step flagged**' if c['step_flagged_factor_only'] else 'no step'} | {c['harmonized_step']:.3f} | "
                 f"{c['modis_step']:.3f} |")
    for v, c in cont.items():
        L.append("")
        L.append(f"In-sample Σ Ñ_V / Σ N_V per overlap year ({v}): " +
                 ", ".join(f"{y}: {x:.2f}" for y, x in c["overlap_pred_over_obs"].items()))
    L += [
          "", "## Breaks at MODIS processing changes (report only)", "",
          "| year | VIIRS fire-days | MODIS fire-days | ratio | MODIS version |", "|---|---|---|---|---|"]
    L += [f"| {x.year} | {x.n_viirs:.0f} | {x.n_modis:.0f} | {x.ratio:.2f} | {x.modis_version} |" for x in ann.itertuples()]
    L += ["", "| period | mean ratio | change vs 2012-2017 | Welch t | flagged (abs t > 2) |", "|---|---|---|---|---|"]
    L += [f"| {p['period']} | {p['mean_ratio']:.2f} | {p['change_vs_2012_2017']:+.1%} | {p['welch_t']:.2f} | {'yes' if p['flagged'] else 'no'} |" for p in per]
    out.write_text("\n".join(L) + "\n")


def run(cfg: dict, region_name: str) -> pd.DataFrame:
    ho = holdout(cfg, region_name)
    cu = counting_units(cfg, region_name)
    rlog = log_correlation(cfg, region_name)
    cont = {name: continuity(cfg, region_name, excl) for name, excl in variants(cfg)}
    ann, per = breaks(cfg, region_name)
    k_sel = pd.DataFrame(read_report(cfg, region_name, "factors").get("k_selection", []))
    write_report(cfg, region_name, ho, cu, rlog, cont, ann, per, k_sel)
    report = {"counting_units": cu.to_dict("records"), "log_corr": rlog, "continuity": cont, "break_periods": per}
    write_stage(cfg, region_name, "holdout", ho, report, ["fire_days", "factors", "factors_boot"])
    write_stage(cfg, region_name, "breaks", ann, {"periods": per}, ["fire_segments"])
    log.info("validate %s: continuity %s", region_name,
             {k: (round(v["step_index"], 3), [round(x, 3) for x in v["band"]]) for k, v in cont.items()})
    return ho
