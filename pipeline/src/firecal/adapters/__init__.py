"""Adapter registry: each format name maps to a function returning the internal schema."""
from __future__ import annotations

from pathlib import Path

from .base import AdapterError
from .firms_csv import firms_api_csv, firms_archive_csv, firms_nrt_csv
from .generic import generic
from .json_ import json_
from .shapefile import shapefile

ADAPTERS = {
    "firms_archive_csv": firms_archive_csv,
    "firms_api_csv": firms_api_csv,
    "firms_nrt_csv": firms_nrt_csv,
    "shapefile": shapefile,
    "json": json_,
    "generic": generic,
}

FIRMS_HEADER = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence"}


def detect_format(path: str | Path) -> str:
    """Guess the format from extension and header. Explicit formats in config are preferred."""
    p = str(path).lower()
    if p.endswith((".shp", ".shp.zip")) or (p.endswith(".zip") and "fire_" in p):
        return "shapefile"
    if p.endswith((".json", ".geojson")):
        return "json"
    if p.endswith((".csv", ".csv.gz", ".txt")):
        import pandas as pd

        head = pd.read_csv(path, nrows=50, dtype=str).rename(columns=str.lower)
        cols = set(head.columns)
        if not FIRMS_HEADER <= cols:
            raise AdapterError(f"{path}: not FIRMS-shaped (columns {sorted(cols)}); use format: generic "
                               "with a column_map")
        nrt_version = "version" in cols and head["version"].astype(str).str.upper().str.contains("NRT").any()
        if "type" not in cols or nrt_version:
            return "firms_nrt_csv"
        if "country" in cols:
            return "firms_archive_csv"
        unpadded = head["acq_time"].str.len().lt(4).any()
        return "firms_api_csv" if unpadded else "firms_archive_csv"
    raise AdapterError(f"{path}: cannot detect format; set `format` in config")


def get_adapter(fmt: str, path: str | Path):
    if fmt == "auto":
        fmt = detect_format(path)
    if fmt not in ADAPTERS:
        raise AdapterError(f"unknown format {fmt!r}; known: {sorted(ADAPTERS)}")
    return fmt, ADAPTERS[fmt]
