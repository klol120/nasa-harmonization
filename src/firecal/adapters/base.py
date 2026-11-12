"""Shared conversion from FIRMS-style columns to the internal schema."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..schema import conform

SATELLITE_MAP = {
    "MODIS": {"terra": "Terra", "t": "Terra", "aqua": "Aqua", "a": "Aqua"},
    "VIIRS": {"n": "SNPP", "npp": "SNPP", "snpp": "SNPP", "suomi npp": "SNPP", "suomi-npp": "SNPP",
              "n20": "NOAA20", "noaa-20": "NOAA20", "noaa20": "NOAA20", "j1": "NOAA20", "1": "NOAA20",
              "n21": "NOAA21", "noaa-21": "NOAA21", "noaa21": "NOAA21", "j2": "NOAA21"},
}
VIIRS_CONFIDENCE = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal", "h": "high", "high": "high"}
SOURCE_SAT = {"SNPP": "SNPP", "NOAA20": "NOAA20", "NOAA21": "NOAA21"}


class AdapterError(ValueError):
    pass


def modis_confidence(values: pd.Series, bins: dict) -> pd.Series:
    c = pd.to_numeric(values, errors="coerce")
    if c.isna().any():
        raise AdapterError(f"non-numeric MODIS confidence: {values[c.isna()].unique()[:5].tolist()}")
    out = pd.Series(pd.NA, index=values.index, dtype="object")
    for cls, (lo, hi) in bins.items():
        out[(c >= lo) & (c <= hi)] = cls
    if out.isna().any():
        raise AdapterError(f"MODIS confidence outside bins: {c[out.isna()].unique()[:5].tolist()}")
    return out


def parse_datetime(acq_date: pd.Series, acq_time: pd.Series) -> pd.Series:
    date = pd.to_datetime(acq_date).dt.strftime("%Y-%m-%d")
    t = acq_time.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.replace(":", "")
    if not t.str.fullmatch(r"\d{1,4}").all():
        raise AdapterError(f"bad acq_time values: {t[~t.str.fullmatch(r'[0-9]{1,4}')].unique()[:5].tolist()}")
    t = t.str.zfill(4)
    return pd.to_datetime(date + " " + t.str[:2] + ":" + t.str[2:], format="%Y-%m-%d %H:%M", utc=True)


def infer_sensor(df: pd.DataFrame, source: str | None) -> pd.Series:
    if "instrument" in df:
        s = df["instrument"].astype(str).str.upper().str.strip()
    elif source:
        s = pd.Series(source.split("_")[0].upper(), index=df.index)
    else:
        raise AdapterError("cannot infer sensor: no instrument column and no source")
    if not s.isin(["MODIS", "VIIRS"]).all():
        raise AdapterError(f"unknown instrument values: {s[~s.isin(['MODIS', 'VIIRS'])].unique()[:5].tolist()}")
    return s


def map_satellite(raw: pd.Series, sensor: pd.Series) -> pd.Series:
    key = raw.astype(str).str.strip().str.lower()
    out = pd.Series(pd.NA, index=raw.index, dtype="object")
    for sen, mapping in SATELLITE_MAP.items():
        m = sensor == sen
        out[m] = key[m].map(mapping)
    if out.isna().any():
        bad = raw[out.isna()].unique()[:5].tolist()
        raise AdapterError(f"unknown satellite values {bad}; extend adapters.base.SATELLITE_MAP")
    return out


def infer_source(sensor: pd.Series, satellite: pd.Series, version: pd.Series) -> pd.Series:
    nrt = version.fillna("").astype(str).str.upper().str.contains("NRT")
    proc = np.where(nrt, "NRT", "SP")
    sat_part = np.where(sensor == "MODIS", "", satellite.map(SOURCE_SAT).fillna("").astype(str) + "_")
    return pd.Series(sensor.astype(str) + "_" + sat_part + proc, index=sensor.index)


def firms_to_schema(df: pd.DataFrame, *, origin: str, input_file: str, source: str | None,
                    modis_bins: dict, country: pd.Series | None = None) -> pd.DataFrame:
    """df has FIRMS column names (lowercase). Returns the internal schema."""
    df = df.rename(columns=str.lower)
    need = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence"]
    missing = [c for c in need if c not in df]
    if missing:
        raise AdapterError(f"{input_file}: missing FIRMS columns {missing}; got {list(df.columns)}")
    if source == "auto":
        source = None
    sensor = infer_sensor(df, source)
    satellite = map_satellite(df["satellite"], sensor)
    conf_raw = df["confidence"].astype(str).str.strip()
    conf = pd.Series(pd.NA, index=df.index, dtype="object")
    m = sensor == "MODIS"
    if m.any():
        conf[m] = modis_confidence(conf_raw[m], modis_bins)
    v = ~m
    if v.any():
        mapped = conf_raw[v].str.lower().map(VIIRS_CONFIDENCE)
        if mapped.isna().any():
            raise AdapterError(f"unknown VIIRS confidence {conf_raw[v][mapped.isna()].unique()[:5].tolist()}")
        conf[v] = mapped
    version = df["version"].astype(str) if "version" in df else pd.Series(pd.NA, index=df.index, dtype="string")
    out = pd.DataFrame({
        "lat": pd.to_numeric(df["latitude"]),
        "lon": pd.to_numeric(df["longitude"]),
        "datetime_utc": parse_datetime(df["acq_date"], df["acq_time"]),
        "sensor": sensor,
        "satellite": satellite,
        "confidence_class": conf,
        "confidence_raw": conf_raw,
        "frp": pd.to_numeric(df["frp"]) if "frp" in df else np.nan,
        "daynight": df["daynight"].astype(str).str.upper().str.strip() if "daynight" in df else pd.NA,
        "fire_type": pd.to_numeric(df["type"]).astype("Int8") if "type" in df else pd.NA,
        "version": version,
        "country": country if country is not None else (df["country"] if "country" in df else pd.NA),
        "source": source if source else infer_source(sensor, satellite, version),
        "origin": origin,
        "input_file": input_file,
    }, index=df.index)
    return conform(out)
