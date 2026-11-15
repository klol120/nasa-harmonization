"""Write backend/firecal_api/live/excluded_cells.json from the firecal pipeline's own stages.

Near-real-time detections have no fire `type`, so the pipeline (stage `clean`) drops them in the 0.01 degree
cells it knows as static land sources or as persistent night-time sources. The live pipeline needs the
same cells to count fire-days the way the exports do. They depend on the whole archive, so they are
taken from the pipeline rather than recomputed.

Run it with the pipeline's Python, after `python -m firecal clean --region <region>`:

    cd pipeline && .venv/bin/python ../backend/tools/export_excluded_cells.py lebanon greece eastmed

Also writes each region's footprint: which 0.01 degree cells of its bbox lie in its countries, by the
pipeline's own country tagging (Natural Earth, a point in the sea takes the nearest country within
footprint.max_sea_km). The pipeline keeps an API detection only if its point is in the region's countries;
the live pipeline applies the same test at 0.01 degree resolution.

Regions already in the file are kept unless named again.
"""

import base64
import json
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from firecal.config import load_config, path
from firecal.geo import cell_index, tag_country
from firecal.io import read_stage
from firecal.stages import clean

OUT = Path(__file__).resolve().parents[1] / "firecal_api" / "live" / "excluded_cells.json"
FINE_COLS = 36000  # 360 / 0.01, as firecal_api.live.harmonize


def key(pcell: str) -> int:
    row, col = pcell.split("_")
    return int(row) * FINE_COLS + int(col)


def footprint(cfg: dict, region: str) -> dict:
    """Bitmap (row-major from the south-west corner) of the bbox's 0.01 degree cells lying in the region's countries."""
    reg = cfg["regions"][region]
    w, s, e, n = reg["bbox"]
    (r0,), (c0,) = cell_index([s], [w], 0.01)
    (r1,), (c1,) = cell_index([n], [e], 0.01)
    rows, cols = np.arange(r0, r1 + 1), np.arange(c0, c1 + 1)
    lat = np.repeat((rows + 0.5) * 0.01 - 90, len(cols))
    lon = np.tile((cols + 0.5) * 0.01 - 180, len(rows))
    tag = tag_country(lat, lon, path(cfg, "boundaries"), cfg["footprint"]["max_sea_km"])
    inside = tag.isin(reg["countries"]).to_numpy()
    bits = base64.b64encode(zlib.compress(np.packbits(inside).tobytes(), 9)).decode()
    return {"row0": int(r0), "col0": int(c0), "rows": len(rows), "cols": len(cols), "inside": int(inside.sum()), "bits": bits}


def main(regions: list[str]) -> None:
    cfg = load_config()
    p = cfg["persistence"]
    if abs(p["cell_deg"] - 0.01) > 1e-12:
        sys.exit(f"persistence.cell_deg is {p['cell_deg']}, the live pipeline expects 0.01")
    doc = json.loads(OUT.read_text()) if OUT.is_file() else {"regions": {}}
    for region in regions:
        static = clean.static_cells(read_stage(cfg, region, "detections"), p)
        stats = read_stage(cfg, region, "persistent_sources")
        persistent = set(stats.pcell[stats.flagged]) if p["mode"] != "off" else set()
        doc["regions"][region] = {
            "static": len(static), "persistent": len(persistent),
            "cells": sorted({key(c) for c in static | persistent}),
            "footprint": footprint(cfg, region),
        }
        fp = doc["regions"][region]["footprint"]
        print(f"{region}: {len(static)} static-source cells, {len(persistent)} persistent cells, "
              f"footprint {fp['inside']} of {fp['rows'] * fp['cols']} fine cells")
    doc.update({
        "cell_deg": p["cell_deg"],
        "rule": f"static: type-2 share of typed detections >= {p['static_min_share']}; persistent: year share >= "
                f"{p['min_year_frac']} and night share >= {p['min_night_frac']} (mode {p['mode']})",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "key": "row * 36000 + col of the 0.01 degree cell",
    })
    OUT.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:] or sys.exit("give at least one region"))
