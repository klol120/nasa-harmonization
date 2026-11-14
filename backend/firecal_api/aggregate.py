"""Area aggregation following the contract's "Aggregating over areas" rules.

- Counts and bands add up over cells.
- anomaly_z is never summed or averaged: it is recomputed from the summed series against the region's
  baseline years, using months with display_only = false, with the sample standard deviation
  (ddof = 1; this reproduces the exported region z exactly). z is null when sd = 0 or no data.
- Region-wide flags come from region_month.
"""

import math
import statistics
from collections.abc import Iterable, Sequence

Ring = Sequence[Sequence[float]]  # [[lon, lat], ...]


def point_in_ring(lon: float, lat: float, ring: Ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_polygon(lon: float, lat: float, polygon: Sequence[Ring]) -> bool:
    """GeoJSON polygon: first ring is the outer boundary, the others are holes."""
    if not polygon or not point_in_ring(lon, lat, polygon[0]):
        return False
    return not any(point_in_ring(lon, lat, hole) for hole in polygon[1:])


def anomaly_z(
    months: Sequence[dict],
    sums: dict,
    baseline: tuple[int, int],
) -> dict:
    """z per month for a summed harmonized series.

    months: region_month rows (ym: date, data_available, display_only), in order.
    sums:   {ym: summed harmonized or None}.
    """
    b0, b1 = baseline
    by_cal: dict[int, list[float]] = {}
    for m in months:
        v = sums.get(m["ym"])
        if b0 <= m["ym"].year <= b1 and not m["display_only"] and m["data_available"] and v is not None:
            by_cal.setdefault(m["ym"].month, []).append(v)
    stats = {}
    for cal, vals in by_cal.items():
        if len(vals) >= 2:
            stats[cal] = (statistics.fmean(vals), statistics.stdev(vals))
    out = {}
    for m in months:
        v = sums.get(m["ym"])
        st = stats.get(m["ym"].month)
        if v is None or not m["data_available"] or st is None or st[1] == 0 or math.isnan(st[1]):
            out[m["ym"]] = None
        else:
            out[m["ym"]] = (v - st[0]) / st[1]
    return out


def select_cells(
    cells: Iterable[dict],
    *,
    cell_ids: set[str] | None = None,
    bbox: Sequence[float] | None = None,
    polygon: Sequence[Ring] | None = None,
    exclude_persistent: bool = False,
) -> list[int]:
    """cell_keys of the region's cells matching every given filter (a cell matches an area by its centre)."""
    out = []
    for c in cells:
        if exclude_persistent and c["is_persistent"]:
            continue
        if cell_ids is not None and c["cell_id"] not in cell_ids:
            continue
        lon, lat = c["lon_center"], c["lat_center"]
        if bbox is not None and not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            continue
        if polygon is not None and not point_in_polygon(lon, lat, polygon):
            continue
        out.append(c["cell_key"])
    return out
