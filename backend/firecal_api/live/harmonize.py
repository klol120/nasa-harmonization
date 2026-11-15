"""Harmonization of live detections: the rules of the firecal pipeline, applied to near-real-time data.

The record's unit is the VIIRS S-NPP fire-day. Suomi NPP stopped delivering data on 2026-11-02; from
2026-11-03 the series continues with NOAA-20 calibrated to S-NPP units (the pipeline's `continuation`
stage, data contract 0.5). Live months follow the same rules as the exports:

1. Which detections count (pipeline stage `clean`):
   - confidence nominal or high (low is dropped);
   - near-real-time rows carry no fire `type`, so the pipeline drops them in the 0.01 degree cells it knows
     as static land sources (mostly type 2 in the archive) or as persistent night-time sources
     (industrial sites, open dumps). Those cells are listed per region in excluded_cells.json, written
     from the pipeline's own stages by tools/export_excluded_cells.py;
   - a detection counts only if its point lies in the region's countries (the pipeline tags API rows with
     Natural Earth and keeps the archive countries); the same file holds that footprint at 0.01 degrees;
   - NOAA-21 is not used.
2. Which satellite a day is counted from: S-NPP up to the day before the switch, NOAA-20 from the switch.
3. Conversion: S-NPP fire-days count as they are; NOAA-20 fire-days are multiplied by c_m (value and
   90 % band), c_m = sum N_SNPP / sum N_NOAA20 per calendar month on the 2018-2025 overlap. The factors
   are read from the release (`meta.calibration.continuation.factors`, contract 0.5); for a release
   exported before 0.5 the frozen values below are used (same numbers, from the 0.5 exports of 2026-11-14).

A region with neither (a new country loaded from a 0.4 export) falls back to factor 1 and its live
months are marked provisional. VERSION is stored with every live month; change it when the rules change
and run `firecal-db live-recompute`.
"""

import base64
import json
import math
import zlib
from datetime import date
from functools import lru_cache
from pathlib import Path

VERSION = "firecal-continuation-1"

# First day counted from NOAA-20 (pipeline config sensors.continuation.switch_date); S-NPP's last data
# is the day before (FIRMS: "satellite ceased at 15:40 UTC on November 2, 2026").
SWITCH_DATE = date(2026, 11, 3)
SNPP_LAST_DAY = date(2026, 11, 2)

# FIRMS VIIRS confidence classes that count (pipeline config clean.confidence_classes: nominal, high).
KEEP_CONFIDENCE = frozenset({"n", "h", "nominal", "high"})

# Simulated detections (demo replay) always count, with factor 1.
SIM = "SIM"

# Fine grid of the static / persistent source cells (pipeline config persistence.cell_deg).
FINE_DEG = 0.01
FINE_COLS = 36000

# c_m, c_low, c_high per calendar month, from meta.calibration.continuation.factors of the contract-0.5
# exports generated 2026-11-14 (strategy `single` for Lebanon and Greece, `local` for EastMed).
_ONE = (1.0, 1.0, 1.0)
FROZEN_FACTORS: dict[str, list[tuple[float, float, float]]] = {
    "lebanon": [(0.9278, 0.8825, 0.9664)] * 12,
    "greece": [(0.9206, 0.8962, 0.9449)] * 12,
    "eastmed": [
        (0.9826, 0.9637, 1.0230), (0.9320, 0.8839, 0.9948), (0.9468, 0.8858, 1.0203), (0.9223, 0.8561, 1.0114),
        (0.9860, 0.9188, 1.0504), (0.9854, 0.9513, 1.0228), (0.9562, 0.8556, 1.0443), (1.0142, 0.9692, 1.0495),
        (0.9930, 0.9585, 1.0192), (0.9760, 0.9602, 0.9887), (0.9020, 0.8573, 0.9407), (0.9525, 0.9217, 1.0020),
    ],
}


class Rules:
    """The harmonization of one region, resolved from its release."""

    def __init__(self, region: str, meta: dict | None = None):
        self.region = region
        cont = ((meta or {}).get("calibration") or {}).get("continuation") or {}
        switch = cont.get("switch_date") or ((meta or {}).get("time") or {}).get("viirs_switch_date")
        self.switch_date = date.fromisoformat(switch) if switch else SWITCH_DATE
        by_month = {f["month"]: (f["c"], f.get("c_low", f["c"]), f.get("c_high", f["c"])) for f in cont.get("factors") or []}
        if len(by_month) == 12:
            self.noaa20, self.factor_source = [by_month[m] for m in range(1, 13)], "release"
        elif region in FROZEN_FACTORS:
            self.noaa20, self.factor_source = FROZEN_FACTORS[region], "frozen-2026-11-14"
        else:
            self.noaa20, self.factor_source = [_ONE] * 12, "none"
        self.excluded = excluded_cells(region)
        self.footprint = footprint(region)
        # Provisional: no calibration for the region, or no list of static sources to drop.
        self.provisional = self.factor_source == "none" or self.excluded is None

    def sensors_for_day(self, day: date) -> tuple[str, ...]:
        """Satellites a day is counted from."""
        return ("SNPP",) if day < self.switch_date else ("NOAA20",)

    def factor(self, sensor: str, month: int) -> tuple[float, float, float]:
        """(value, low, high) multiplier from one satellite's fire-days to S-NPP-equivalent fire-days."""
        return self.noaa20[month - 1] if sensor == "NOAA20" else _ONE

    def keep(self, confidence: str | None, lat: float, lon: float) -> bool:
        """Does a near-real-time detection count as a vegetation fire?"""
        if confidence is not None and confidence.lower() not in KEEP_CONFIDENCE:
            return False
        if self.footprint is not None and not self.footprint.contains(lat, lon):
            return False
        return not (self.excluded and fine_key(lat, lon) in self.excluded)

    def fire_days(self, rows, *, include_simulated: bool) -> dict[int, dict[str, int]]:
        """Count fire-days per cell and satellite.

        rows: (cell_key, day, sensor, confidence, simulated, lat, lon). A cell-day counts once per
        satellite, and only for the satellite the day is counted from. Returns {cell_key: {sensor: n}};
        "NOAA20_all" also counts NOAA-20 on the days before the switch (the contract's noaa20_raw).
        """
        seen: set[tuple[int, date, str]] = set()
        for cell_key, day, sensor, confidence, simulated, lat, lon in rows:
            if simulated:
                if include_simulated:
                    seen.add((cell_key, day, SIM))
            elif sensor in ("SNPP", "NOAA20") and self.keep(confidence, lat, lon):
                seen.add((cell_key, day, sensor))
        out: dict[int, dict[str, int]] = {}
        sim_days = {(c, d) for c, d, s in seen if s == SIM}
        for cell_key, day, sensor in seen:
            per = out.setdefault(cell_key, {})
            if sensor == "NOAA20":
                per["NOAA20_all"] = per.get("NOAA20_all", 0) + 1
            if sensor == SIM or sensor in self.sensors_for_day(day):
                # A simulated fire on a cell-day a real satellite also saw is not counted twice.
                if sensor != SIM and (cell_key, day) in sim_days:
                    continue
                per[sensor] = per.get(sensor, 0) + 1
        return out

    def to_snpp_equivalent(self, counts: dict[str, int], month: int) -> tuple[float, float, float]:
        """Harmonized value and 90 % band for one cell-month from its fire-days per satellite."""
        h = lo = hi = 0.0
        for sensor, n in counts.items():
            if sensor == "NOAA20_all":
                continue
            a, a_lo, a_hi = self.factor(sensor, month)
            h, lo, hi = h + a * n, lo + a_lo * n, hi + a_hi * n
        return h, lo, hi


def fine_rc(lat: float, lon: float) -> tuple[int, int]:
    """Row and column of the 0.01 degree cell holding a point (the pipeline's geo.cell_index, same epsilon)."""
    return math.floor((lat + 90) / FINE_DEG + 1e-9), math.floor((lon + 180) / FINE_DEG + 1e-9)


def fine_key(lat: float, lon: float) -> int:
    r, c = fine_rc(lat, lon)
    return r * FINE_COLS + c


class Footprint:
    """Which 0.01 degree cells of a region's bbox lie in its countries."""

    def __init__(self, d: dict):
        self.row0, self.col0, self.rows, self.cols = d["row0"], d["col0"], d["rows"], d["cols"]
        self.bits = zlib.decompress(base64.b64decode(d["bits"]))

    def contains(self, lat: float, lon: float) -> bool:
        r, c = fine_rc(lat, lon)
        r, c = r - self.row0, c - self.col0
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return False
        i = r * self.cols + c
        return bool(self.bits[i >> 3] & (0x80 >> (i & 7)))


@lru_cache(maxsize=None)
def footprint(region: str) -> Footprint | None:
    d = (_excluded_file()["regions"].get(region) or {}).get("footprint")
    return Footprint(d) if d else None


@lru_cache(maxsize=None)
def _excluded_file() -> dict:
    p = Path(__file__).with_name("excluded_cells.json")
    return json.loads(p.read_text()) if p.is_file() else {"regions": {}}


@lru_cache(maxsize=None)
def excluded_cells(region: str) -> frozenset[int] | None:
    """0.01 degree cells whose untyped detections the pipeline drops in this region; None if not listed."""
    r = _excluded_file()["regions"].get(region)
    return None if r is None else frozenset(r["cells"])
