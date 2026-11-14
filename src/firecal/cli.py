"""python -m firecal <stage>|all|auto-strategy --region R [--config PATH]"""
from __future__ import annotations

import argparse
import json
import logging

from .auto_strategy import decide
from .config import load_config
from .stages import anomalies, calibrate, clean, continuation, export, grid, ingest, splice, terra, validate

STAGES = {"ingest": ingest.run, "clean": clean.run, "grid": grid.run, "terra": terra.run,
          "calibrate": calibrate.run, "continuation": continuation.run, "validate": validate.run, "splice": splice.run,
          "anomalies": anomalies.run, "export": export.run}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="firecal")
    ap.add_argument("stage", choices=[*STAGES, "all", "auto-strategy"])
    ap.add_argument("--region", required=True, nargs="+")
    ap.add_argument("--config")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    if args.stage == "auto-strategy":           # print the data-thinness rule's pick (add-country)
        for region in args.region:
            print(json.dumps({"region": region, **decide(cfg, region)}, indent=1))
        return
    for region in args.region:
        for name in (STAGES if args.stage == "all" else [args.stage]):
            STAGES[name](cfg, region)


if __name__ == "__main__":
    main()
