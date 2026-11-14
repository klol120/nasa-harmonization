"""Fire-day unit (method step 1): a cell with at least one detection on a UTC day."""
from __future__ import annotations

import pandas as pd

from .geo import cell_id


def fire_days(df: pd.DataFrame, size: float) -> pd.DataFrame:
    """Unique (cell_id, date, sensor, satellite) rows. MODIS Terra ∪ Aqua = unique (cell, date) per sensor."""
    out = pd.DataFrame({
        "cell_id": cell_id(df.lat.values, df.lon.values, size).values,
        "date": df.datetime_utc.dt.tz_convert(None).dt.normalize().values,
        "sensor": df.sensor.astype(str).values,
        "satellite": df.satellite.astype(str).values,
    })
    return out.drop_duplicates(ignore_index=True)


def count_by_sensor(df: pd.DataFrame, size: float) -> pd.Series:
    """Number of fire-days per sensor (satellites merged)."""
    fd = fire_days(df, size)
    return fd.drop_duplicates(["cell_id", "date", "sensor"]).groupby("sensor").size()
