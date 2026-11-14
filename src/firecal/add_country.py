"""python -m firecal add-country <Country>: a new country end to end.

  1. region     bbox from Natural Earth (polygon parts >= bbox_min_part_share of the largest, so remote
                islands such as the Azores do not stretch it), countries = [Country]. Written to
                config.d/<region>.yaml, with a donor pool that excludes the country when it belongs to
                the default pool.
  2. download   country archives (tools/download_firms.py archives) and the area API for the current
                year (api --assemble). The MAP_KEY handling and redaction stay in the downloader.
  3. ingest, clean, grid
  4. strategy   auto_strategy.decide (data-thinness thresholds, docs/reports/thresholds.md); kT follows
                the same outcome (thin -> single, as Lebanon; rich -> local; donor_only -> donor pool).
                Thin countries take the observed-VIIRS anomaly baseline, as Lebanon.
  5. terra, calibrate, continuation (NOAA-20 strategy = lowest mean hold-out WAPE of the two folds)
  6. validate, splice, anomalies, export
  7. grade      add_country.grades on hold-out WAPE/bias of the chosen strategy and the 2012 continuity
  8. backend    load the export into the teammate backend (local branch only) and check the API lists it

Writes docs/reports/countries/<region>.md and .json.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .auto_strategy import decide
from .config import ROOT, load_config, path, region_settings
from .fitting import FitSpec, chosen, table
from .geo import _boundaries
from .io import read_report, read_stage, stage_file

log = logging.getLogger(__name__)
TERRA_FOR = {"rich": "local", "thin": "single"}          # donor_only: the donor pool (see run)


def slug(country: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", country.lower()).strip("_")


def country_bbox(cfg: dict, country: str) -> list[float]:
    """Bounds of the country's polygon parts that are >= min share of its largest part, padded."""
    ac = cfg["add_country"]
    ne = _boundaries(str(path(cfg, "boundaries")))
    geom = ne[ne.ADMIN == country]
    if geom.empty:
        raise SystemExit(f"{country!r} is not a Natural Earth ADMIN name")
    parts = geom.explode(index_parts=False).geometry
    area = parts.to_crs(6933).area
    keep = parts[area >= ac["bbox_min_part_share"] * area.max()]
    w, s, e, n = keep.total_bounds
    pad = ac["bbox_pad_deg"]
    return [round(float(w) - pad, 2), round(float(s) - pad, 2), round(float(e) + pad, 2), round(float(n) + pad, 2)]


def overlay_path(cfg: dict, region: str) -> Path:
    return Path(cfg["_root"]) / cfg["paths"]["config_d"] / f"{region}.yaml"


def write_overlay(cfg: dict, region: str, body: dict, note: str) -> None:
    p = overlay_path(cfg, region)
    p.parent.mkdir(parents=True, exist_ok=True)
    head = (f"# Written by `python -m firecal add-country` on {dt.date.today()}. Merged over config.yaml "
            f"(paths.config_d).\n# {note}\n")
    p.write_text(head + yaml.safe_dump(body, sort_keys=False, default_flow_style=None, width=110))


def region_overlay(cfg: dict, country: str, region: str) -> dict:
    """Region, plus a pool that excludes the country when it is part of the default outcome pool."""
    body = {"regions": {region: {"bbox": country_bbox(cfg, country), "countries": [country]}}}
    outcomes = dict(cfg["auto_strategy"]["outcomes"])
    pool_name = outcomes["donor_only"].partition(":")[2]
    pool = cfg["donors"][pool_name]
    if country in pool["countries"]:
        g = f"{pool_name}_ex_{region}"
        body["donors"] = {g: {"region": pool["region"], "countries": [c for c in pool["countries"] if c != country],
                              "for_regions": [region]}}
        comp_name = outcomes["thin"]
        comp = cfg["calibration"]["composites"][comp_name]
        shape_kind = comp["shape"].partition(":")[0]
        body["calibration"] = {"composites": {f"{comp_name}_ex_{region}": {"shape": f"{shape_kind}:{g}", "level": comp["level"]}}}
        body["auto_strategy"] = {"by_region": {region: {"outcomes": {
            "donor_only": f"donor:{g}", "thin": f"{comp_name}_ex_{region}", "rich": outcomes["rich"]}}}}
    return body


def stages(cfg: dict, region: str, names: list[str], timings: dict, label: str) -> None:
    from .cli import STAGES

    t = time.time()
    for name in names:
        STAGES[name](cfg, region)
    timings[label] = round(time.time() - t, 1)


def download(cfg: dict, region: str, timings: dict, skip: bool) -> None:
    if skip:
        timings["download"] = 0.0
        return
    t = time.time()
    tool = str(ROOT / "tools/download_firms.py")
    start = dt.date(cfg["download"]["api_year"], 1, 1)
    for args in (["archives", "--regions", region],
                 ["api", "--start", str(start), "--end", str(dt.date.today()), "--regions", region, "--assemble"]):
        r = subprocess.run([sys.executable, tool, *args], cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"download {args[0]} failed:\n{r.stderr[-2000:]}")   # downloader redacts the key
    timings["download"] = round(time.time() - t, 1)


def pick_continuation(cfg: dict, region: str) -> tuple[str, list[dict]]:
    ho = pd.DataFrame(read_report(cfg, region, "cont_factors")["holdout"])
    score = ho.groupby("strategy").wape.mean().sort_values()
    return str(score.index[0]), [{"strategy": s, "mean_wape": round(float(v), 4)} for s, v in score.items()]


def summary(cfg: dict, region: str, decision: dict, cont_rank: list[dict], timings: dict) -> dict:
    variant = "persistence_excluded" if cfg["persistence"]["exclude_from_calibration"] else "pdf_rules"
    pick = chosen(cfg, "calibration", region)
    ho = read_stage(cfg, region, "holdout")
    ho = ho[(ho.variant == variant) & (ho.strategy == pick)].set_index("fold")
    cont = read_report(cfg, region, "holdout")["continuity"][variant]
    y0, y1 = cfg["calibration"]["overlap_years"]
    t = table(cfg, region, FitSpec("a", list(range(y0, y1 + 1)), cfg["persistence"]["exclude_from_calibration"]))
    det = json.loads(stage_file(cfg, region, "detections").with_suffix(".json").read_text())
    clean = json.loads(stage_file(cfg, region, "detections_clean").with_suffix(".json").read_text())
    meta = json.loads((path(cfg, "export") / region / "meta.json").read_text())
    level = meta["calibration"]["factors"]
    s = {
        "region": region, "countries": cfg["regions"][region]["countries"], "bbox": cfg["regions"][region]["bbox"],
        "detections": {"raw": int(det["rows"]), "clean": int(clean["rows"]),
                       "by_source": det["report"].get("by_source")},
        "strategy": pick, "auto": {k: decision[k] for k in ("outcome", "reason", "inputs", "thresholds")},
        "auto_months": [{k: m[k] for k in ("name", "n", "thin", "rule")} for m in decision["months"]],
        "terra_strategy": chosen(cfg, "terra", region),
        "continuation_strategy": chosen(cfg, "continuation", region), "continuation_ranking": cont_rank,
        "ratio": {"viirs_over_modis_2012_2020": round(float(t.num.sum() / t.den.sum()), 3) if t.den.sum() else None,
                  "a_by_month": [round(f["a"], 3) for f in level],
                  "a_band_by_month": [[round(f["a_low"], 3), round(f["a_high"], 3)] for f in level]},
        "holdout": {fold: {"wape": round(float(ho.wape[fold]), 3), "bias": round(float(ho.bias[fold]), 3)}
                    for fold in ("forward", "reverse") if fold in ho.index},
        "continuity_2012": {"step_index": round(cont["step_index"], 3), "band": [round(x, 3) for x in cont["band"]],
                            "flagged": cont["step_flagged"]},
        "continuation": {k: meta["calibration"]["continuation"]["continuity"][k] for k in ("step_index", "band", "step_flagged")}
        if meta["calibration"].get("continuation") else None,
        "n_cells": meta["n_cells"], "timings_s": timings,
    }
    s["grade"], s["grade_reason"] = grade(cfg, s)
    return s


def grade(cfg: dict, s: dict) -> tuple[str, str]:
    """add_country.grades on mean hold-out WAPE (both folds), worst |bias|, and the 2012 step."""
    if s["auto"]["outcome"] == "donor_only":
        return "D", "donor pool only: too few local MODIS fire-days for a local calibration"
    if s["continuity_2012"]["flagged"]:
        return "D", f"artificial step at 2012 (step index {s['continuity_2012']['step_index']}, outside its band)"
    w = float(np.mean([v["wape"] for v in s["holdout"].values()]))
    b = float(max(abs(v["bias"]) for v in s["holdout"].values()))
    for g, lim in cfg["add_country"]["grades"].items():
        if w <= lim["max_wape"] and b <= lim["max_abs_bias"]:
            return g, f"mean hold-out WAPE {w:.3f} <= {lim['max_wape']}, worst |bias| {b:.1%} <= {lim['max_abs_bias']:.0%}, no step at 2012"
    return "D", f"mean hold-out WAPE {w:.3f}, worst |bias| {b:.1%}: beyond every grade"


def load_backend(cfg: dict, region: str, timings: dict) -> dict:
    """Load the export into the teammate backend (must be on its local contract branch) and ask its API."""
    import requests

    b = cfg["add_country"]["backend"]
    repo = (Path(cfg["_root"]) / b["repo"]).resolve()
    out = {"loaded": False, "listed_by_api": False}
    if not repo.is_dir():
        out["error"] = f"{repo} not found"
        return out
    branch = subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    if branch != b["branch"]:
        out["error"] = f"teammate repo is on {branch!r}, expected {b['branch']!r}; not loaded"
        return out
    t = time.time()
    folder = (path(cfg, "export") / region).resolve()
    r = subprocess.run([str(repo / b["python"]), "-m", "firecal_api.cli", "ingest", str(folder)], cwd=repo / "backend",
                       capture_output=True, text=True)
    timings["backend"] = round(time.time() - t, 1)
    out["loaded"] = r.returncode == 0
    out["log_tail"] = (r.stdout + r.stderr).strip().splitlines()[-3:]
    try:
        regs = requests.get(f"{b['api']}/regions", timeout=10).json()
        hit = [x for x in regs if x["region"] == region]
        out["listed_by_api"] = bool(hit)
        if hit:
            out["release_id"], out["contract_version"] = hit[0]["release_id"], hit[0]["contract_version"]
    except Exception as e:                    # API not running: loaded but not checked
        out["error"] = f"API not reachable at {b['api']}: {e.__class__.__name__}"
    return out


def write_reports(cfg: dict, s: dict) -> None:
    d = path(cfg, "reports") / "countries"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{s['region']}.json").write_text(json.dumps(s, indent=1, default=str))
    m = s["auto_months"]
    L = [f"# {s['countries'][0]} ({s['region']}): add-country report", "",
         f"Added {dt.date.today()} by `python -m firecal add-country {s['countries'][0]}`. Config: "
         f"`config.d/{s['region']}.yaml`. bbox {s['bbox']}, {s['n_cells']} cells.", "",
         f"**Quality grade {s['grade']}.** {s['grade_reason']}.", "",
         "| item | value |", "|---|---|",
         f"| detections | {s['detections']['raw']:,} raw, {s['detections']['clean']:,} after cleaning |",
         f"| strategy | `{s['strategy']}` ({s['auto']['outcome']}): {s['auto']['reason']} |",
         f"| kT strategy | `{s['terra_strategy']}` |",
         f"| VIIRS/MODIS fire-days 2012–2020 | {s['ratio']['viirs_over_modis_2012_2020']} |",
         "| hold-out (forward / reverse) | " + " / ".join(f"WAPE {v['wape']:.3f}, bias {v['bias']:+.1%}" for v in s["holdout"].values()) + " |",
         f"| step at 2012 | {s['continuity_2012']['step_index']} (band {s['continuity_2012']['band']}) "
         f"{'**flagged**' if s['continuity_2012']['flagged'] else 'no step'} |"]
    if s["continuation"]:
        c = s["continuation"]
        L.append(f"| NOAA-20 switch (`{s['continuation_strategy']}`) | step {c['step_index']:.3f}, band "
                 f"[{c['band'][0]:.3f}, {c['band'][1]:.3f}] {'**flagged**' if c['step_flagged'] else 'no step'} |")
    L.append(f"| backend | {'loaded' if s['backend'].get('loaded') else 'not loaded'}, "
             f"{'listed by the API' if s['backend'].get('listed_by_api') else 'not listed'}"
             f"{' — ' + s['backend']['error'] if s['backend'].get('error') else ''} |")
    L.append("| runtime (s) | " + ", ".join(f"{k} {v}" for k, v in s["timings_s"].items()) + " |")
    L += ["", "## Strategy rule by month", "", "| month | n (MODIS fire-days 2012–2020) | thin | rule | a |", "|---|---|---|---|---|"]
    for x, a in zip(m, s["ratio"]["a_by_month"]):
        L.append(f"| {x['name']} | {x['n']} | {'thin' if x['thin'] else ''} | {x['rule']} | {a} |")
    (d / f"{s['region']}.md").write_text("\n".join(L) + "\n")


def run(country: str, region: str | None = None, skip_download: bool = False, backend: bool = True) -> dict:
    t0 = time.time()
    cfg = load_config()
    region = region or slug(country)
    timings: dict = {}
    body = region_overlay(cfg, country, region)
    write_overlay(cfg, region, body, f"{country}: region and donors; strategies are added after gridding.")
    cfg = load_config()
    download(cfg, region, timings, skip_download)
    stages(cfg, region, ["ingest", "clean", "grid"], timings, "ingest_clean_grid")

    decision = decide(cfg, region)
    if not decision["available"]:
        raise SystemExit(f"{region}: strategy {decision['strategy']} has no usable donor group")
    outcome = decision["outcome"]
    outs = region_settings(cfg, "auto_strategy", region)["outcomes"]
    terra = TERRA_FOR.get(outcome, outs["donor_only"])
    body.setdefault("calibration", {})["strategy"] = {region: decision["strategy"]}
    body["terra"] = {"strategy": {region: terra}}
    if outcome != "rich":                     # thin regions: observed-VIIRS anomaly baseline, as Lebanon
        body["anomalies"] = {"by_region": {region: cfg["add_country"]["thin_anomalies"]}}
    body["add_country"] = {"regions": {region: {"added": str(dt.date.today()), "outcome": outcome,
                                                "reason": decision["reason"]}}}
    write_overlay(cfg, region, body, f"{country}: auto_strategy {outcome} -> {decision['strategy']} ({decision['reason']}).")
    cfg = load_config()
    stages(cfg, region, ["terra", "calibrate", "continuation"], timings, "terra_calibrate_continuation")

    cont_pick, cont_rank = pick_continuation(cfg, region)
    body["continuation"] = {"strategy": {region: cont_pick}}
    write_overlay(cfg, region, body, f"{country}: auto_strategy {outcome} -> {decision['strategy']} ({decision['reason']}); "
                                     f"NOAA-20 transfer {cont_pick} (lowest mean hold-out WAPE).")
    cfg = load_config()
    stages(cfg, region, ["continuation"], timings, "continuation_final")      # with the chosen strategy
    stages(cfg, region, ["validate", "splice", "anomalies", "export"], timings, "validate_splice_anomalies_export")

    s = summary(cfg, region, decide(cfg, region), cont_rank, timings)
    s["backend"] = load_backend(cfg, region, timings) if backend else {"loaded": False, "error": "skipped (--no-backend)"}
    timings["total"] = round(time.time() - t0, 1)
    write_reports(cfg, s)
    log.info("add-country %s: grade %s, strategy %s, %.0fs", region, s["grade"], s["strategy"], timings["total"])
    return s
