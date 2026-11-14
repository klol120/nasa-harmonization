"""Export the frontend files described in docs/data_contract.md."""
from __future__ import annotations

import datetime as dt
import json
import logging

import numpy as np
import pandas as pd

from .. import __version__
from ..config import as_date, config_hash, continuation, path, region_settings, stage_dir
from ..fitting import chosen, composite_spec
from ..io import read_report, read_stage
from ..outages import runs

log = logging.getLogger(__name__)
CONTRACT_VERSION = "0.5"
# Per-cell values only; region-wide flags live in region_monthly (contract 0.4).
CALENDAR_COLUMNS = {
    "cell_id": "string", "ym": "string", "year": "int16", "month": "int8", "modis_raw": "Int16",
    "viirs_raw": "Int16", "noaa20_raw": "Int16", "harmonized": "float32", "harmonized_low": "float32", "harmonized_high": "float32",
    "anomaly_z": "float32",
}
FLAG_COLUMNS = ["is_estimate", "has_gap", "data_available", "partial_month", "display_only", "low_confidence"]
REGION_COLUMNS = ["ym", "year", "month", "modis_raw", "viirs_raw", "noaa20_raw", "harmonized", "harmonized_low",
                  "harmonized_high", "anomaly_z", "source", *FLAG_COLUMNS, "n_cells", "n_persistent_cells"]
SERIES_FIELDS = {"h": "harmonized", "m": "modis_raw", "v": "viirs_raw"}


def ym(year, month) -> pd.Series:
    return pd.Series(year).astype(int).astype(str).str.zfill(4).values + "-" + \
        pd.Series(month).astype(int).astype(str).str.zfill(2).values


def calendar(cfg, region) -> pd.DataFrame:
    h = read_stage(cfg, region, "anomalies")
    h["ym"] = ym(h.year, h.month)
    return h[list(CALENDAR_COLUMNS)].astype(CALENDAR_COLUMNS)


def cell_series(cal: pd.DataFrame, reg: pd.DataFrame) -> dict[int, dict]:
    """Per-year compact files: {cell_id: {h, m, v: [12 monthly values]}}.

    Cells with no fire-day in the year (all values 0 or null) are omitted: read them as 0 in months
    where the region has data (region_monthly.data_available) and null otherwise."""
    out = {}
    for year, g in cal.groupby("year"):
        months = reg[reg.year == year].sort_values("month")
        ms = months.month.tolist()
        g = g[g.month.isin(ms)]
        active = g.groupby("cell_id", observed=True)[["harmonized", "modis_raw", "viirs_raw"]] \
            .apply(lambda x: bool((x.fillna(0) != 0).any().any()))
        g = g[g.cell_id.isin(active.index[active])]
        cells = {}
        for cid, c in g.sort_values("month").groupby("cell_id", observed=True):
            cells[cid] = {k: [None if pd.isna(v) else (round(float(v), 2) if k == "h" else int(v))
                              for v in c[f].tolist()] for k, f in SERIES_FIELDS.items()}
        out[int(year)] = {"contract_version": CONTRACT_VERSION, "year": int(year), "ym": months.ym.tolist(),
                          "fields": SERIES_FIELDS, "omitted_cells": "no fire-days this year: 0 where data_available, else null",
                          "cells": cells}
    return out


def region_table(cfg, region, cells) -> pd.DataFrame:
    r = read_stage(cfg, region, "region_monthly")
    r["n_persistent_cells"] = int(cells.is_persistent.sum())
    r["ym"] = ym(r.year, r.month)
    r = r[REGION_COLUMNS].copy()
    for c in ("harmonized", "harmonized_low", "harmonized_high", "anomaly_z"):
        r[c] = r[c].astype("float32")
    r["modis_raw"] = r.modis_raw.round().astype("Int32")
    r["viirs_raw"] = r.viirs_raw.round().astype("Int32")
    r["noaa20_raw"] = r.noaa20_raw.round().astype("Int32")
    r["source"] = r.source.astype(object).where(r.source.notna(), None)
    return r


def _json_value(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
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


def meta(cfg, region, cal: pd.DataFrame, cells, files: dict | None = None) -> dict:
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
    first, last = cal.ym.min(), cal.ym.max()
    sources = {p: {"satellites": ["Terra", "Aqua"] if p.startswith("MODIS") else [p.split("_")[1]],
                   "first_date": str(as_date(a)), "last_date": str(as_date(b))} for p, (a, b) in cov.items()}
    cont = continuation(cfg)
    return {
        "contract_version": CONTRACT_VERSION, "region": region, "bbox": r["bbox"], "countries": r["countries"],
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "pipeline": {"version": __version__, "config_hash": config_hash(cfg)},
        "formats_status": "pending confirmation from the frontend team",
        "units": f"VIIRS-equivalent fire-days per {cfg['grid']['size_deg']}° cell per month",
        "n_cells": int(len(cells)), "n_persistent_cells": int(cells.is_persistent.sum()),
        "files": files or {},
        "time": {"first_month": first, "last_month": last,
                 "stats_last_year": cfg["years"]["stats_last_year"],
                 "display_only_years": sorted(int(y) for y in cal.year.unique() if y > cfg["years"]["stats_last_year"]),
                 "splice_date": str(as_date(cfg["sensors"]["viirs_start"])),
                 "terra_only_until": str(as_date(cfg["sensors"]["terra_only_until"])),
                 "viirs_switch_date": str(cont["switch_date"]) if cont else None},
        "sources": sources,
        "source_values": {"MODIS": "estimate converted from MODIS (is_estimate)", "SNPP": "observed VIIRS S-NPP",
                          "NOAA20": "VIIRS NOAA-20 calibrated to S-NPP units (calibration.continuation)",
                          "A+B": "month split between two sources at a switch date (e.g. MODIS+SNPP, SNPP+NOAA20)"},
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
            "continuation": continuation_meta(cfg, region) if cont else None,
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
            *(["From the VIIRS switch date (S-NPP's end) harmonized is NOAA-20 calibrated to S-NPP units per calendar "
               "month (source = NOAA20); viirs_raw stays S-NPP only, noaa20_raw is the uncalibrated NOAA-20 count."]
              if cont else []),
            "is_persistent cells contain persistent (industrial / waste-burning) sources; they are excluded from "
            "calibration but kept in the data so the UI can show or hide them.",
        ],
    }


def continuation_meta(cfg, region) -> dict:
    rep = read_report(cfg, region, "cont_factors")
    f = read_stage(cfg, region, "cont_factors").query("strategy == @rep['strategy']")
    ho = pd.DataFrame(rep["holdout"])
    c = rep["continuity"]
    return {"satellite": rep["satellite"], "replaces": rep["replaces"], "switch_date": rep["switch_date"],
            "strategy": rep["strategy"], "overlap_years": rep["overlap_years"],
            "factors": records(f[["month", "a", "a_low", "a_high"]].rename(
                columns={"a": "c", "a_low": "c_low", "a_high": "c_high"})),
            "holdout": records(ho[ho.fold == "forward"][["strategy", "k", "wape", "bias"]].sort_values("wape")),
            "continuity": {k: c[k] for k in ("window", "step_index", "band", "step_flagged", "raw_ratio")}}


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
    _, gj = cells_json(cfg, cells)
    (out / "cells.geojson").write_text(json.dumps(gj))
    (out / "cells.json").unlink(missing_ok=True)          # dropped in contract 0.4 (geometry is in cells.geojson)
    sdir = out / "cells_series"
    sdir.mkdir(exist_ok=True)
    for f in sdir.glob("*.json"):
        f.unlink()
    for year, doc in cell_series(cal, reg).items():
        (sdir / f"{year}.json").write_text(json.dumps(doc, separators=(",", ":")))
    files = {p.relative_to(out).as_posix(): p.stat().st_size for p in sorted(out.rglob("*")) if p.is_file()
             and p.name != "meta.json"}
    (out / "meta.json").write_text(json.dumps(meta(cfg, region_name, cal, cells, files), indent=2, default=_json_value))
    log.info("export %s: %d rows, %d cells -> %s", region_name, len(cal), len(cells), out)
    return cal
