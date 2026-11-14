"""VIIRS continuation: NOAA-20 calibrated to S-NPP units, for the months after S-NPP's end.

c_m = sum_y N_SNPP / sum_y N_NOAA20 per calendar month over continuation.overlap_years, on dates both
satellites have data and no flagged outage (fitting.TARGETS["c"]), with the same strategies and year
bootstrap as the MODIS -> VIIRS calibration. Validation:
  - hold-out per strategy (fit/test split of the overlap, and the reverse fold);
  - continuity at the switch: on the days between the end of the overlap years and the switch, both
    satellites observe, so the calibrated NOAA-20 total can be compared with the S-NPP total the series
    would have carried without the switch. step_index = sum c_m N_NOAA20 / sum N_SNPP (out of sample);
    about 1 means no artificial step. The 90% band combines the c_m bootstrap with the year-to-year
    spread of observed / predicted S-NPP on the overlap years.
"""
from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from ..calibration import wape_bias
from ..config import continuation, path
from ..fitting import (TARGETS, FitSpec, chosen, ensure_fire_days, expand_strategies, fit_all, predict_table,
                       table, usable_dates)
from ..io import read_stage, write_stage

log = logging.getLogger(__name__)


def years(span) -> list[int]:
    return list(range(span[0], span[1] + 1))


def holdout(cfg: dict, region: str, strategies: list[str], excl: bool) -> pd.DataFrame:
    h = cfg["continuation"]["holdout"]
    fit, test = years(h["fit"]), years(h["test"])
    rows = []
    for fold, (fy, ty) in {"forward": (fit, test), "reverse": (test, fit)}.items():
        lt = table(cfg, region, FitSpec("c", ty, excl))
        for strat in strategies:
            pred, k = predict_table(cfg, region, strat, fy, lt, excl, target="c")
            wape, bias = wape_bias(lt.num, pred)
            rows.append({"fold": fold, "fit": f"{fy[0]}-{fy[-1]}", "test": f"{ty[0]}-{ty[-1]}", "strategy": strat,
                         "k": k, "wape": wape, "bias": bias, "test_snpp": float(lt.num.sum()),
                         "test_noaa20": float(lt.den.sum())})
    return pd.DataFrame(rows)


def check_window(cfg: dict, switch: dt.date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Days after the overlap years and before the switch: both satellites observe, out of sample."""
    y1 = cfg["continuation"]["overlap_years"][1]
    return pd.Timestamp(y1 + 1, 1, 1), pd.Timestamp(switch) - pd.Timedelta(days=1)


def continuity(cfg: dict, region: str, fac: pd.DataFrame, boot: pd.DataFrame, strategy: str, excl: bool,
               switch: dt.date) -> dict:
    sfx = "_np" if excl else ""
    t = TARGETS["c"]
    fd = ensure_fire_days(cfg, region)
    fd = fd[usable_dates(cfg, fd, read_stage(cfg, region, "outages"), t["sats"])]
    w0, w1 = check_window(cfg, switch)
    win = fd[fd.date.between(w0, w1)]
    by_m = win.groupby(win.date.dt.to_period("M"))[[f"viirs{sfx}", f"noaa20{sfx}"]].sum()
    by_m.columns = ["snpp", "noaa20"]
    c = fac[fac.strategy == strategy].set_index("month").a
    C = boot[boot.strategy == strategy].pivot(index="draw", columns="month", values="a")
    months = by_m.index.month.to_numpy()
    by_m["pred"] = by_m.noaa20.to_numpy() * c.reindex(months).to_numpy()
    obs, pred = by_m.snpp.sum(), by_m.pred.sum()
    idx = pred / obs
    draws = (C[months].to_numpy() * by_m.noaa20.to_numpy()).sum(1) / obs

    # year-to-year spread of obs / pred on the overlap (in sample), as for the 2012 continuity band
    ov = table(cfg, region, FitSpec("c", years(cfg["continuation"]["overlap_years"]), excl))
    yp = (ov.den * c.to_numpy()).sum(1)
    ok = yp > 0
    ratio = ov.num.sum(1)[ok] / yp[ok]
    rng = np.random.default_rng(cfg["calibration"]["bootstrap"]["seed"])
    noise = rng.choice(ratio, len(draws)) / ratio.mean()
    ci = cfg["calibration"]["bootstrap"]["ci"]
    lo, hi = np.nanquantile(draws / noise, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    olo, ohi = np.nanquantile(draws, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    per_year = pd.Series(yp[ok] / ov.num.sum(1)[ok], index=ov.years[ok])
    return {"strategy": strategy, "exclude_persistent": excl, "window": [str(w0.date()), str(w1.date())],
            "snpp_observed": float(obs), "noaa20_raw": float(by_m.noaa20.sum()), "noaa20_calibrated": float(pred),
            "step_index": float(idx), "band": [float(lo), float(hi)], "step_flagged": bool(not lo <= 1 <= hi),
            "band_factor_only": [float(olo), float(ohi)],
            "raw_ratio": float(by_m.noaa20.sum() / obs),
            "by_month": [{"ym": str(p), "snpp": int(r.snpp), "noaa20": int(r.noaa20), "calibrated": round(float(r.pred), 2)}
                         for p, r in by_m.iterrows()],
            "overlap_pred_over_obs": {int(y): round(float(v), 3) for y, v in per_year.items()}}


def write_report(cfg, region, fac, ho, cont, pick, switch) -> None:
    out = path(cfg, "reports") / f"{region}_continuation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    c = cfg["sensors"]["continuation"]
    y0, y1 = cfg["continuation"]["overlap_years"]
    f = fac[fac.strategy == pick].set_index("month")
    L = [f"# {region}: VIIRS continuation ({c['satellite']} calibrated to {c['replaces']})", "",
         f"From {switch} the harmonized series is c_m × NOAA-20 fire-days (S-NPP's last data: "
         f"{switch - dt.timedelta(days=1)}). c_m = Σ N_SNPP / Σ N_NOAA20 per calendar month over {y0}-{y1}, on days "
         "both satellites have data and no flagged outage, persistent-source fire-days excluded. "
         f"Strategy used: `{pick}`. 90% bands: year bootstrap (B = {cfg['calibration']['bootstrap']['n']}).", "",
         "## Factors", "", "| month | c | 90% band | S-NPP fire-days | NOAA-20 fire-days | raw ratio |", "|---|---|---|---|---|---|"]
    for m, r in f.iterrows():
        raw = r.n_local_num / r.n_local_den if r.n_local_den else float("nan")
        L.append(f"| {m} | {r.a:.3f} | [{r.a_low:.3f}, {r.a_high:.3f}] | {r.n_local_num:.0f} | {r.n_local_den:.0f} | {raw:.3f} |")
    s = fac[fac.strategy == "single"]
    if len(s):
        L += ["", f"All months pooled (`single`): c = {s.a.iloc[0]:.3f} [{s.a_low.iloc[0]:.3f}, {s.a_high.iloc[0]:.3f}]."]
    h = cfg["continuation"]["holdout"]
    L += ["", f"## Hold-out (monthly totals): fit {h['fit'][0]}-{h['fit'][1]}, test {h['test'][0]}-{h['test'][1]}", "",
          "| strategy | k | WAPE | bias | WAPE (reverse) | bias (reverse) |", "|---|---|---|---|---|---|"]
    fw = ho[ho.fold == "forward"].set_index("strategy")
    rv = ho[ho.fold == "reverse"].set_index("strategy")
    for st, x in fw.sort_values("wape").iterrows():
        k = "" if pd.isna(x.k) else f"{x.k:g}"
        L.append(f"| {st} | {k} | {x.wape:.3f} | {x.bias:+.1%} | {rv.loc[st].wape:.3f} | {rv.loc[st].bias:+.1%} |")
    L += ["", "## Continuity at the switch", "",
          f"Window {cont['window'][0]} to {cont['window'][1]} (after the fit years, before the switch; both satellites "
          "observe). Step index = Σ c_m N_NOAA20 / Σ N_SNPP: the level the series takes after the switch relative to "
          "the level it would have had with S-NPP. About 1 = no artificial step. The band adds the year-to-year spread "
          "of observed / predicted on the overlap to the factor bootstrap.", "",
          "| S-NPP | NOAA-20 raw | NOAA-20 calibrated | raw ratio | step index | 90% band | result | band (factor bootstrap only) |",
          "|---|---|---|---|---|---|---|---|",
          f"| {cont['snpp_observed']:.0f} | {cont['noaa20_raw']:.0f} | {cont['noaa20_calibrated']:.1f} | "
          f"{cont['raw_ratio']:.3f} | {cont['step_index']:.3f} | [{cont['band'][0]:.3f}, {cont['band'][1]:.3f}] | "
          f"{'**step flagged**' if cont['step_flagged'] else 'no step'} | "
          f"[{cont['band_factor_only'][0]:.3f}, {cont['band_factor_only'][1]:.3f}] |", "",
          "| month | S-NPP | NOAA-20 | NOAA-20 calibrated |", "|---|---|---|---|"]
    L += [f"| {r['ym']} | {r['snpp']} | {r['noaa20']} | {r['calibrated']:.1f} |" for r in cont["by_month"]]
    L += ["", "In-sample Σ ĉ N_NOAA20 / Σ N_SNPP per overlap year: " +
          ", ".join(f"{y}: {v:.2f}" for y, v in cont["overlap_pred_over_obs"].items())]
    out.write_text("\n".join(L) + "\n")


def run(cfg: dict, region_name: str):
    c = continuation(cfg)
    if not c:
        log.info("continuation %s: not configured, skipped", region_name)
        return None
    excl = cfg["persistence"]["exclude_from_calibration"]
    spec = FitSpec("c", years(cfg["continuation"]["overlap_years"]), excl)
    strategies = expand_strategies(cfg, region_name, cfg["continuation"]["strategies"])
    pick = chosen(cfg, "continuation", region_name)
    if pick not in strategies:
        strategies.append(pick)
    fac, boot, kt = fit_all(cfg, region_name, spec, strategies)
    ho = holdout(cfg, region_name, strategies, excl)
    cont = continuity(cfg, region_name, fac, boot, pick, excl, c["switch_date"])
    write_report(cfg, region_name, fac, ho, cont, pick, c["switch_date"])
    report = {"strategy": pick, "satellite": c["satellite"], "replaces": c["replaces"],
              "switch_date": str(c["switch_date"]), "overlap_years": cfg["continuation"]["overlap_years"],
              "exclude_persistent": excl, "strategies": strategies,
              "c": fac[fac.strategy == pick].set_index("month").a.round(4).to_dict(),
              "continuity": cont, "holdout": ho.to_dict("records"), "k_selection": kt.to_dict("records")}
    write_stage(cfg, region_name, "cont_factors", fac, report, ["fire_days", "outages"])
    write_stage(cfg, region_name, "cont_boot", boot, None, ["fire_days"])
    log.info("continuation %s (%s): step %.3f band %s", region_name, pick, cont["step_index"], cont["band"])
    return fac
