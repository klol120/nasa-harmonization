"""Export the frontend files described in docs/data_contract.md."""
from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from .. import __version__
from ..config import as_date, config_hash, path, region_settings, stage_dir
from ..fitting import chosen, composite_spec
from ..io import read_report, read_stage
from ..outages import runs

log = logging.getLogger(__name__)
CONTRACT_VERSION = "0.3"
CALENDAR_COLUMNS = {
    "cell_id": "string", "year": "int16", "month": "int8", "modis_raw": "Int16", "viirs_raw": "Int16",
    "harmonized": "float32", "harmonized_low": "float32", "harmonized_high": "float32",
    "is_estimate": "bool", "has_gap": "bool", "data_available": "bool", "partial_month": "bool",
    "display_only": "bool", "low_confidence": "bool", "is_persistent": "bool", "anomaly_z": "float32",
}
REGION_COLUMNS = [c for c in CALENDAR_COLUMNS if c not in ("cell_id", "is_persistent")] + ["n_cells", "n_persistent_cells"]


def calendar(cfg, region) -> pd.DataFrame:
    h = read_stage(cfg, region, "anomalies")
    return h[list(CALENDAR_COLUMNS)].astype(CALENDAR_COLUMNS)


def region_table(cfg, region, cells) -> pd.DataFrame:
    r = read_stage(cfg, region, "region_monthly")
    r["n_persistent_cells"] = int(cells.is_persistent.sum())
    r = r[REGION_COLUMNS].copy()
    for c in ("harmonized", "harmonized_low", "harmonized_high", "anomaly_z"):
        r[c] = r[c].astype("float32")
    r["modis_raw"] = r.modis_raw.round().astype("Int32")
    r["viirs_raw"] = r.viirs_raw.round().astype("Int32")
    return r


def _json_value(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: _json_value(v) for k, v in row.items()} for row in df.astype(object).to_dict("records")]


def cells_json(cfg, cells: pd.DataFrame) -> tuple[dict, dict]:
    size = cfg["grid"]["size_deg"]
    out = []
    for c in cells.itertuples():
        w, s = round(c.col * size - 180, 6), round(c.row * size - 90, 6)
        out.append({"cell_id": c.cell_id, "row": int(c.row), "col": int(c.col), "lat_center": float(c.lat_center),
                    "lon_center": float(c.lon_center), "bounds": [w, s, round(w + size, 6), round(s + size, 6)],
                    "countries": [x for x in c.countries.split("|") if x],
                    "primary_country": c.primary_country if isinstance(c.primary_country, str) else None,
                    "is_persistent": bool(c.is_persistent)})
    rule = ("row = floor((lat + 90) / {g}), col = floor((lon + 180) / {g}), cell_id = f'{{row}}_{{col}}'"
            .format(g=size))
    cj = {"contract_version": CONTRACT_VERSION, "grid_size_deg": size, "cell_id_rule": rule, "cells": out}
    feats = [{"type": "Feature", "properties": {k: v for k, v in c.items() if k != "bounds"},
              "geometry": {"type": "Polygon", "coordinates": [[[c["bounds"][0], c["bounds"][1]], [c["bounds"][2], c["bounds"][1]],
                                                                [c["bounds"][2], c["bounds"][3]], [c["bounds"][0], c["bounds"][3]],
                                                                [c["bounds"][0], c["bounds"][1]]]]}} for c in out]
    return cj, {"type": "FeatureCollection", "features": feats}


def meta(cfg, region, cal: pd.DataFrame, cells) -> dict:
    r = cfg["regions"][region]
    pick, pick_k = chosen(cfg, "calibration", region), chosen(cfg, "terra", region)
    allfac = read_stage(cfg, region, "factors")
    comp = composite_spec(cfg, pick)
    fac = allfac[allfac.strategy == (comp["level"] if comp else pick)]
    fcols = ["month", "a", "a_low", "a_high", "b", "b_low", "b_high", "w_local"]
    kt = read_stage(cfg, region, "kT").query("strategy == @pick_k")
    ho = read_stage(cfg, region, "holdout")
    hrep = read_report(cfg, region, "holdout")
    srep = read_report(cfg, region, "harmonized")
    arep = read_report(cfg, region, "anomalies")
    variant = "persistence_excluded" if cfg["persistence"]["exclude_from_calibration"] else "pdf_rules"
    fwd = ho[(ho.fold == "forward") & (ho.variant == variant)]
    outages = read_stage(cfg, region, "outages")
    cov = cfg["coverage"]
    ym = cal.year.astype(int) * 12 + cal.month.astype(int) - 1
    first = pd.Series({"year": ym.min() // 12, "month": ym.min() % 12 + 1})
    last = pd.Series({"year": ym.max() // 12, "month": ym.max() % 12 + 1})
    return {
        "contract_version": CONTRACT_VERSION, "region": region, "bbox": r["bbox"], "countries": r["countries"],
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "pipeline": {"version": __version__, "config_hash": config_hash(cfg)},
        "formats_status": "pending confirmation from the frontend team",
        "units": f"VIIRS-equivalent fire-days per {cfg['grid']['size_deg']}° cell per month",
        "n_cells": int(len(cells)), "n_persistent_cells": int(cells.is_persistent.sum()),
        "time": {"first_month": f"{int(first.year)}-{int(first.month):02d}", "last_month": f"{int(last.year)}-{int(last.month):02d}",
                 "stats_last_year": cfg["years"]["stats_last_year"],
                 "display_only_years": sorted(int(y) for y in cal.year[cal.display_only].unique()),
                 "splice_date": str(as_date(cfg["sensors"]["viirs_start"])),
                 "terra_only_until": str(as_date(cfg["sensors"]["terra_only_until"]))},
        "sources": {"MODIS_SP": {"satellites": ["Terra", "Aqua"], "first_date": str(as_date(cov["MODIS_SP"][0])),
                                 "last_date": str(as_date(cov["MODIS_SP"][1]))},
                    "VIIRS_SNPP_SP": {"satellites": ["SNPP"], "first_date": str(as_date(cov["VIIRS_SNPP_SP"][0])),
                                      "last_date": str(as_date(cov["VIIRS_SNPP_SP"][1]))}},
        "calibration": {
            "strategy": pick, "overlap_years": cfg["calibration"]["overlap_years"],
            "exclude_persistent_from_fit": cfg["persistence"]["exclude_from_calibration"],
            "blend_k": None if fac.k.isna().all() else float(fac.k.iloc[0]),
            "factors": records(fac[fcols]),
            "composite": None if not comp else {
                "description": "monthly shape from `shape`, each year's estimated total from `level`; "
                               "`factors` above are the level model's",
                "shape": {"strategy": comp["shape"],
                          "k": _json_value(allfac[allfac.strategy == comp["shape"]].k.iloc[0]),
                          "factors": records(allfac[allfac.strategy == comp["shape"]][fcols])},
                "level": {"strategy": comp["level"], "factors": records(fac[fcols])},
                "bands": "level model's factor uncertainty only (shape uncertainty not propagated)"},
            "terra_strategy": pick_k,
            "terra_correction": records(kt[["month", "kT", "kT_low", "kT_high"]]),
        },
        "low_confidence_rule": {**region_settings(cfg, "low_confidence", region),
                                "months": [int(m["month"]) for m in srep["low_confidence_months"] if m["low_confidence"]],
                                "by_month": [{k: _json_value(v) for k, v in m.items()} for m in srep["low_confidence_months"]]},
        "validation": {
            "variant": variant, "holdout": cfg["calibration"]["holdout"],
            "strategies": records(fwd[["strategy", "k", "wape", "bias"]].sort_values("wape")),
            "continuity_2012": {k: hrep["continuity"][variant][k] for k in
                                ("step_index", "band", "step_flagged", "band_factor_only", "step_flagged_factor_only")},
        },
        "anomalies": {"baseline_years": region_settings(cfg, "anomalies", region)["baseline_years"],
                      "baseline_source": "anomalies.by_region" if region in (cfg["anomalies"].get("by_region") or {}) else "anomalies",
                      "method": "z-score per cell and calendar month",
                      "sensitivity": [{"baseline_years": s["baseline_years"], "region_corr_z": s["region"]["corr_z"],
                                       "region_mean_abs_dz": s["region"]["mean_abs_dz"],
                                       "cells_corr_z": s["cells_all_months"]["corr_z"],
                                       "cells_mean_abs_dz": s["cells_all_months"]["mean_abs_dz"]} for s in arep["sensitivity"]]},
        "outages": [{"satellite": x.satellite, "start": f"{x.start:%Y-%m-%d}", "end": f"{x.end:%Y-%m-%d}"}
                    for x in runs(outages[outages.flagged]).itertuples()],
        "caveats": [
            "Pre-2012 values are estimates converted from MODIS and must be labelled as such.",
            "low_confidence marks pre-2012 months where MODIS sees almost none of the VIIRS-detected activity or the "
            "factor rests on few MODIS fire-days; show them with extra caution.",
            "Fire-days measure burning activity, not burned area.",
            "2026 is a partial year shown for display only.",
            "is_persistent cells contain persistent (industrial / waste-burning) sources; they are excluded from "
            "calibration but kept in the data so the UI can show or hide them.",
        ],
    }


def run(cfg: dict, region_name: str) -> pd.DataFrame:
    out = path(cfg, "export") / region_name
    out.mkdir(parents=True, exist_ok=True)
    cal = calendar(cfg, region_name)
    cells = read_stage(cfg, region_name, "cells")
    reg = region_table(cfg, region_name, cells)
    cal.to_parquet(out / "calendar.parquet", index=False)
    cal.to_csv(out / "calendar.csv.gz", index=False, float_format="%.4g", compression="gzip")
    reg.to_csv(out / "region_monthly.csv", index=False, float_format="%.4f")
    (out / "region_monthly.json").write_text(json.dumps(records(reg)))
    cj, gj = cells_json(cfg, cells)
    (out / "cells.json").write_text(json.dumps(cj))
    (out / "cells.geojson").write_text(json.dumps(gj))
    (out / "meta.json").write_text(json.dumps(meta(cfg, region_name, cal, cells), indent=2, default=_json_value))
    log.info("export %s: %d rows, %d cells -> %s", region_name, len(cal), len(cells), out)
    return cal
