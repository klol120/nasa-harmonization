"""Data contract v0.4/v0.5: constants and the small pure helpers shared by ingest, API and tests."""

import math
from datetime import date

# Contract versions this backend can load. A rename/removal/type change bumps the version,
# so anything else is refused rather than half-loaded.
SUPPORTED_CONTRACT_VERSIONS = {"0.4", "0.5"}

GRID_DEG = 0.05
GRID_COLS = 7200  # 360 / 0.05

REGION_MONTH_FIELDS = (
    "ym", "year", "month", "modis_raw", "viirs_raw", "noaa20_raw", "harmonized", "harmonized_low", "harmonized_high",
    "anomaly_z", "source", "is_estimate", "has_gap", "data_available", "partial_month", "display_only",
    "low_confidence", "n_cells", "n_persistent_cells",
)
REGION_MONTH_FLAGS = ("is_estimate", "has_gap", "data_available", "partial_month", "display_only", "low_confidence")

CALENDAR_FIELDS = (
    "cell_id", "ym", "year", "month", "modis_raw", "viirs_raw", "noaa20_raw",
    "harmonized", "harmonized_low", "harmonized_high", "anomaly_z",
)
# Values that add up over cells (contract: "Counts and bands add up").
ADDITIVE_FIELDS = ("modis_raw", "viirs_raw", "noaa20_raw", "harmonized", "harmonized_low", "harmonized_high")

# Added in v0.5 (NOAA-20 continuation of VIIRS after S-NPP's end); absent from v0.4 exports.
OPTIONAL_CALENDAR_FIELDS = ("noaa20_raw",)
# region_monthly.source values that mean harmonized is observed S-NPP / calibrated NOAA-20.
SOURCE_SNPP, SOURCE_NOAA20 = "SNPP", "NOAA20"

SERIES_FIELDS = {"h": "harmonized", "m": "modis_raw", "v": "viirs_raw"}


class ContractError(ValueError):
    """The export does not satisfy the data contract."""


def cell_rc(lat: float, lon: float) -> tuple[int, int]:
    """Global grid row/col of the cell containing (lat, lon)."""
    # Small epsilon: centres like 33.075 must not fall to the cell below through float error.
    return math.floor((lat + 90) / GRID_DEG + 1e-9), math.floor((lon + 180) / GRID_DEG + 1e-9)


def cell_id(row: int, col: int) -> str:
    return f"{row}_{col}"


def cell_key(row: int, col: int) -> int:
    return row * GRID_COLS + col


def parse_cell_id(cid: str) -> tuple[int, int]:
    try:
        r, c = cid.split("_")
        return int(r), int(c)
    except ValueError:
        raise ContractError(f"bad cell_id {cid!r}") from None


def parse_ym(s: str) -> date:
    try:
        y, m = s.split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        raise ContractError(f"bad ym {s!r}, expected 'YYYY-MM'") from None


def ym_str(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_range(first: date, last: date) -> list[date]:
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def check_version(v: str | None, where: str) -> None:
    if v not in SUPPORTED_CONTRACT_VERSIONS:
        raise ContractError(
            f"{where}: contract_version {v!r} is not supported (supported: {sorted(SUPPORTED_CONTRACT_VERSIONS)})"
        )
