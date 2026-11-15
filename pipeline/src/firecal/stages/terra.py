"""Terra-only correction (method step 2): kT(m) = sum_y N_T∪A / sum_y N_T over terra.fit_years."""
from __future__ import annotations

import logging

from ..fitting import FitSpec, chosen, expand_strategies, fit_all
from ..io import write_stage

log = logging.getLogger(__name__)


def run(cfg: dict, region_name: str):
    y0, y1 = cfg["terra"]["fit_years"]
    spec = FitSpec("kT", list(range(y0, y1 + 1)), cfg["persistence"]["exclude_from_calibration"])
    strategies = expand_strategies(cfg, region_name, cfg["terra"].get("strategies", ["single", "local"]))
    pick = chosen(cfg, "terra", region_name)
    if pick not in strategies:
        strategies.append(pick)
    f, d, kt = fit_all(cfg, region_name, spec, strategies)
    f = f.rename(columns={"a": "kT", "a_low": "kT_low", "a_high": "kT_high"})
    report = {"strategy": pick, "fit_years": [y0, y1], "exclude_persistent": spec.exclude_persistent,
              "kT_overall": float(f[f.strategy == "single"].kT.iloc[0]) if "single" in strategies else None,
              "kT": f[f.strategy == pick].set_index("month").kT.round(3).to_dict(), "k_selection": kt.to_dict("records")}
    write_stage(cfg, region_name, "kT", f, report, ["fire_days", "outages"])
    write_stage(cfg, region_name, "kT_boot", d.rename(columns={"a": "kT"}), None, ["fire_days"])
    log.info("terra %s: %s", region_name, report["kT"])
    return f
