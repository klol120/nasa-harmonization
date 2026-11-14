"""Ingest: config `inputs` -> adapters -> internal schema, clipped to the region footprint."""
from __future__ import annotations

import glob
import logging
from pathlib import Path

import pandas as pd

from ..adapters import get_adapter
from ..config import path, region
from ..geo import in_bbox, tag_country
from ..io import write_stage
from ..schema import conform, empty_detections

log = logging.getLogger(__name__)
ADAPTER_OPTIONS = ("column_map", "constants", "read")


def input_files(cfg: dict, region_name: str, spec: dict) -> list[Path]:
    pattern = spec["path"].format(region=region_name, raw=path(cfg, "raw"))
    if not Path(pattern).is_absolute():
        pattern = str(Path(cfg["_root"]) / pattern)
    return [Path(f) for f in sorted(glob.glob(pattern))]


def run(cfg: dict, region_name: str) -> pd.DataFrame:
    r = region(cfg, region_name)
    root = Path(cfg["_root"])
    frames, report = [], {"inputs": [], "countries": r["countries"], "bbox": r["bbox"]}
    for spec in cfg["inputs"]:
        files = input_files(cfg, region_name, spec)
        if not files:
            log.warning("no files match %s", spec["path"])
        for f in files:
            fmt, adapter = get_adapter(spec.get("format", "auto"), f)
            rel = str(f.relative_to(root)) if f.is_relative_to(root) else str(f)
            df = adapter(f, input_file=rel, source=spec.get("source"),
                         modis_bins=cfg["clean"]["modis_confidence_bins"],
                         **{k: spec[k] for k in ADAPTER_OPTIONS if k in spec})
            untagged = df.country.isna()
            if untagged.any():
                df.loc[untagged, "country"] = tag_country(
                    df.lat[untagged], df.lon[untagged], path(cfg, "boundaries"),
                    cfg["footprint"]["max_sea_km"]).values
            keep = df.country.isin(r["countries"]).to_numpy() & in_bbox(df.lat, df.lon, r["bbox"])
            report["inputs"].append({"file": rel, "format": fmt, "rows": len(df), "kept": int(keep.sum()),
                                     "tagged": int(untagged.sum())})
            frames.append(df[keep])
    df = conform(pd.concat(frames, ignore_index=True)) if frames else empty_detections()
    report["rows"] = len(df)
    report["by_source"] = df.groupby("source", observed=True).size().to_dict()
    write_stage(cfg, region_name, "detections", df, report, [i["file"] for i in report["inputs"]])
    log.info("ingest %s: %d rows from %d files", region_name, len(df), len(report["inputs"]))
    return df
