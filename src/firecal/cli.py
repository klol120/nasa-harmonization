"""python -m firecal <stage>|all --region R [--config PATH]"""
from __future__ import annotations

import argparse
import logging

from .config import load_config
from .stages import anomalies, calibrate, clean, export, grid, ingest, splice, terra, validate

STAGES = {"ingest": ingest.run, "clean": clean.run, "grid": grid.run, "terra": terra.run,
          "calibrate": calibrate.run, "validate": validate.run, "splice": splice.run,
          "anomalies": anomalies.run, "export": export.run}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="firecal")
    ap.add_argument("stage", choices=[*STAGES, "all"])
    ap.add_argument("--region", required=True, nargs="+")
    ap.add_argument("--config")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    for region in args.region:
        for name in (STAGES if args.stage == "all" else [args.stage]):
            STAGES[name](cfg, region)


if __name__ == "__main__":
    main()
