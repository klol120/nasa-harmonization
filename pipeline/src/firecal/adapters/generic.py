"""Any delimited table, mapped to FIRMS names with a config column_map.

Example input entry:
  {path: "data/hack/*.csv", format: generic, source: VIIRS_SNPP_NRT,
   column_map: {latitude: lat_dd, longitude: lon_dd, acq_date: date, acq_time: hhmm,
                satellite: sat, confidence: conf, instrument: sensor},
   constants: {instrument: VIIRS}, read: {sep: ";"}}
"""
from __future__ import annotations

import pandas as pd

from .base import firms_to_schema


def generic(path, *, input_file: str, source: str | None, modis_bins: dict,
            column_map: dict | None = None, constants: dict | None = None, read: dict | None = None,
            **_) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, **(read or {}))
    df = df.rename(columns={v: k for k, v in (column_map or {}).items()})
    for k, v in (constants or {}).items():
        df[k] = v
    return firms_to_schema(df, origin="generic", input_file=input_file, source=source, modis_bins=modis_bins)
