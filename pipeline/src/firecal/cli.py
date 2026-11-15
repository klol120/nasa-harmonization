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


def add_country_main(argv):
    from .add_country import run

    ap = argparse.ArgumentParser(prog="firecal add-country")
    ap.add_argument("country", help="Natural Earth ADMIN name, e.g. Jordan")
    ap.add_argument("--region", help="region id (default: lowercase country)")
    ap.add_argument("--skip-download", action="store_true", help="use raw files already in data/raw")
    ap.add_argument("--no-backend", action="store_true", help="do not load into the teammate backend")
    args = ap.parse_args(argv)
    s = run(args.country, args.region, args.skip_download, not args.no_backend)
    print(json.dumps({k: s[k] for k in ("region", "strategy", "grade", "grade_reason", "holdout", "continuity_2012",
                                        "backend", "timings_s")}, indent=1, default=str))


def main(argv=None):
    import sys

    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if argv and argv[0] == "add-country":
        return add_country_main(argv[1:])
    ap = argparse.ArgumentParser(prog="firecal")
    ap.add_argument("stage", choices=[*STAGES, "all", "auto-strategy"])
    ap.add_argument("--region", required=True, nargs="+")
    ap.add_argument("--config")
    args = ap.parse_args(argv)
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
