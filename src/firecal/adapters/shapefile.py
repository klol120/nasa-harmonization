"""FIRMS shapefile downloads (fire_archive_*.shp / fire_nrt_*.shp, also zipped).

DBF field names are truncated/uppercased (LATITUDE, ACQ_DATE, ...); ACQ_DATE may be a date field.
Coordinates fall back to the point geometry when LATITUDE/LONGITUDE are absent.
"""
from __future__ import annotations

import pandas as pd

from .base import firms_to_schema


def shapefile(path, *, input_file: str, source: str | None, modis_bins: dict, **_) -> pd.DataFrame:
    import geopandas as gpd

    g = gpd.read_file(path)
    df = pd.DataFrame(g.drop(columns="geometry")).rename(columns=str.lower)
    if "latitude" not in df:
        df["latitude"], df["longitude"] = g.geometry.y.values, g.geometry.x.values
    origin = "nrt" if "nrt" in str(path).lower() else "shapefile"
    return firms_to_schema(df, origin=origin, input_file=input_file, source=source, modis_bins=modis_bins)
