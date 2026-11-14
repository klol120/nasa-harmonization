"""Internal detection schema shared by every adapter and stage."""
from __future__ import annotations

import pandas as pd

SENSORS = ["MODIS", "VIIRS"]
SATELLITES = ["Terra", "Aqua", "SNPP", "NOAA20", "NOAA21"]
CONFIDENCE = ["low", "nominal", "high"]
DAYNIGHT = ["D", "N"]
ORIGINS = ["archive", "api", "nrt", "shapefile", "json", "generic"]

# column -> pandas dtype
DETECTION_COLUMNS: dict[str, object] = {
    "lat": "float64",
    "lon": "float64",
    "datetime_utc": "datetime64[us, UTC]",
    "sensor": pd.CategoricalDtype(SENSORS),
    "satellite": pd.CategoricalDtype(SATELLITES),
    "confidence_class": pd.CategoricalDtype(CONFIDENCE),
    "confidence_raw": "string",
    "frp": "float32",
    "daynight": pd.CategoricalDtype(DAYNIGHT),
    "fire_type": "Int8",
    "version": "string",
    "country": "string",
    "source": "string",
    "origin": pd.CategoricalDtype(ORIGINS),
    "input_file": "string",
}
NOT_NULL = ["lat", "lon", "datetime_utc", "sensor", "satellite", "confidence_class", "source", "origin"]


class SchemaError(ValueError):
    pass


def empty_detections() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in DETECTION_COLUMNS.items()})


def conform(df: pd.DataFrame) -> pd.DataFrame:
    """Order columns and cast to the schema dtypes; raises SchemaError on bad values."""
    missing = [c for c in DETECTION_COLUMNS if c not in df]
    if missing:
        raise SchemaError(f"missing columns: {missing}")
    out = df[list(DETECTION_COLUMNS)].copy()
    for col, dtype in DETECTION_COLUMNS.items():
        if isinstance(dtype, pd.CategoricalDtype):
            bad = set(out[col].dropna().unique()) - set(dtype.categories)
            if bad:
                raise SchemaError(f"{col}: unexpected values {sorted(map(str, bad))[:10]}")
        out[col] = out[col].astype(dtype)
    validate(out)
    return out.reset_index(drop=True)


def validate(df: pd.DataFrame) -> None:
    if list(df.columns) != list(DETECTION_COLUMNS):
        raise SchemaError(f"columns {list(df.columns)} != schema")
    for col, dtype in DETECTION_COLUMNS.items():
        if str(df[col].dtype) != str(pd.Series(dtype=dtype).dtype):
            raise SchemaError(f"{col}: dtype {df[col].dtype}, expected {dtype}")
    nulls = [c for c in NOT_NULL if df[c].isna().any()]
    if nulls:
        raise SchemaError(f"nulls in required columns: {nulls}")
    if not (df.lat.between(-90, 90).all() and df.lon.between(-180, 180).all()):
        raise SchemaError("lat/lon out of range")
