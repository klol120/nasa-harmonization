"""Phase 0 entry point for country tagging; the implementation lives in firecal.geo."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from firecal.geo import tag_country as _tag  # noqa: E402

NE_PATH = ROOT / "data/ext/ne_10m_admin_0_countries.zip"


def tag_country(df: pd.DataFrame, max_sea_km: float = 12.0) -> pd.Series:
    """Country per row of a FIRMS frame (latitude/longitude columns); NA where none applies."""
    s = _tag(df.latitude.values, df.longitude.values, NE_PATH, max_sea_km)
    s.index = df.index
    return s
