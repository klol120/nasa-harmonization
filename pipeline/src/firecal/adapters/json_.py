"""JSON inputs: an array of FIRMS records, {"data"|"records"|"features": [...]}, or GeoJSON."""
from __future__ import annotations

import json

import pandas as pd

from .base import AdapterError, firms_to_schema


def _records(obj) -> list[dict]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if obj.get("type") == "FeatureCollection":
            rows = []
            for f in obj["features"]:
                p = dict(f.get("properties") or {})
                lower = {k.lower() for k in p}
                if "latitude" not in lower and (f.get("geometry") or {}).get("type") == "Point":
                    p["longitude"], p["latitude"] = f["geometry"]["coordinates"][:2]
                rows.append(p)
            return rows
        for key in ("data", "records", "features", "fires"):
            if isinstance(obj.get(key), list):
                return obj[key]
    raise AdapterError("unrecognised JSON layout: expected a list, {data:[...]}, or a FeatureCollection")


def json_(path, *, input_file: str, source: str | None, modis_bins: dict, **_) -> pd.DataFrame:
    with open(path) as fh:
        rows = _records(json.load(fh))
    df = pd.DataFrame(rows)
    for col in ("acq_time", "confidence", "version", "satellite"):
        match = [c for c in df.columns if c.lower() == col]
        if match:
            df[match[0]] = df[match[0]].astype(str)
    return firms_to_schema(df, origin="json", input_file=input_file, source=source, modis_bins=modis_bins)
