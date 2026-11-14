"""FIRMS CSV variants: country archive, area API, NRT.

Observed columns (data/raw, 2026-11): latitude, longitude, brightness|bright_ti4, scan, track, acq_date,
acq_time, satellite, instrument, confidence, version, bright_t31|bright_ti5, frp, daynight, type
(+ country in our region files). The API does not zero-pad acq_time. NRT files have no `type`
and a version ending in "NRT".
"""
from __future__ import annotations

import pandas as pd

from .base import firms_to_schema

READ_DTYPES = {"acq_time": str, "confidence": str, "version": str, "satellite": str, "country": str}


def _read(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=READ_DTYPES, keep_default_na=False, na_values=[""])


def _make(origin: str):
    def adapter(path, *, input_file: str, source: str | None, modis_bins: dict, **_) -> pd.DataFrame:
        return firms_to_schema(_read(path), origin=origin, input_file=input_file, source=source,
                               modis_bins=modis_bins)
    adapter.__name__ = f"firms_{origin}_csv"
    return adapter


firms_archive_csv = _make("archive")
firms_api_csv = _make("api")
firms_nrt_csv = _make("nrt")
