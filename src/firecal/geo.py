"""Grid cells and country tagging."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

EPS = 1e-9  # guards floor() against float error on cell edges


def cell_index(lat, lon, size: float) -> tuple[np.ndarray, np.ndarray]:
    row = np.floor((np.asarray(lat, dtype=float) + 90) / size + EPS).astype(np.int64)
    col = np.floor((np.asarray(lon, dtype=float) + 180) / size + EPS).astype(np.int64)
    return row, col


def cell_id(lat, lon, size: float) -> pd.Series:
    row, col = cell_index(lat, lon, size)
    return pd.Series(row.astype(str), dtype="object") + "_" + pd.Series(col.astype(str), dtype="object")


def cell_bounds(cid: str, size: float) -> tuple[float, float, float, float]:
    """(west, south, east, north) of a cell_id."""
    row, col = (int(x) for x in cid.split("_"))
    s, w = row * size - 90, col * size - 180
    return round(w, 9), round(s, 9), round(w + size, 9), round(s + size, 9)


def in_bbox(lat, lon, bbox) -> np.ndarray:
    w, s, e, n = bbox
    lat, lon = np.asarray(lat), np.asarray(lon)
    return (lat >= s) & (lat <= n) & (lon >= w) & (lon <= e)


@lru_cache(maxsize=2)
def _boundaries(path: str):
    import geopandas as gpd

    return gpd.read_file(path)[["ADMIN", "geometry"]]


def tag_country(lat, lon, boundaries: str | Path, max_sea_km: float = 12.0) -> pd.Series:
    """Country (Natural Earth ADMIN) per point; NA where none applies.

    FIRMS country archives use a finer coastline than Natural Earth 10m, so a point in NE's sea
    takes the nearest country within max_sea_km (Phase 0: archives reach 12 km into NE's sea).
    """
    import geopandas as gpd

    ne = _boundaries(str(boundaries))
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(np.asarray(lon), np.asarray(lat)), crs=4326)
    j = gpd.sjoin(pts, ne, how="left", predicate="within")
    country = j[~j.index.duplicated()].ADMIN.reindex(pts.index).astype("string")
    sea = country.isna()
    if sea.any() and max_sea_km > 0:
        n = gpd.sjoin_nearest(pts[sea].to_crs(3035), ne.to_crs(3035), distance_col="dist")
        n = n[~n.index.duplicated()]
        near = n.dist <= max_sea_km * 1000
        country.loc[n.index[near]] = n.ADMIN[near].values
    return country
