"""Monthly calibration (method step 3) on the overlap years, every strategy, year-bootstrap bands."""
from __future__ import annotations

import logging

from ..fitting import FitSpec, chosen, expand_strategies, fit_all
from ..io import write_stage

log = logging.getLogger(__name__)


def run(cfg: dict, region_name: str):
    y0, y1 = cfg["calibration"]["overlap_years"]
    spec = FitSpec("a", list(range(y0, y1 + 1)), cfg["persistence"]["exclude_from_calibration"])
    strategies = expand_strategies(cfg, region_name, cfg["calibration"]["strategies"])
    pick = chosen(cfg, "calibration", region_name)
    if pick not in strategies:
        strategies.append(pick)   # e.g. an affine strategy chosen in config but not in the comparison list
    f, d, kt = fit_all(cfg, region_name, spec, strategies)
    report = {"strategy": pick, "overlap_years": [y0, y1], "exclude_persistent": spec.exclude_persistent,
              "strategies": strategies, "a": f[f.strategy == pick].set_index("month").a.round(3).to_dict(),
              "k_selection": kt.to_dict("records")}
    write_stage(cfg, region_name, "factors", f, report, ["fire_days", "outages"])
    write_stage(cfg, region_name, "factors_boot", d, None, ["fire_days"])
    log.info("calibrate %s (%s): %s", region_name, pick, report["a"])
    return f
