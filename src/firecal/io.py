"""Stage file I/O: Parquet tables with a JSON sidecar recording provenance."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from . import __version__
from .config import config_hash, stage_dir

LAYERS = {
    "detections": "interim", "detections_clean": "interim", "persistent_sources": "interim",
    "outages": "interim", "fire_days": "interim", "fire_segments": "interim", "segments": "interim", "kT": "interim", "kT_boot": "interim",
    "factors": "processed", "factors_boot": "processed", "holdout": "processed", "breaks": "processed",
    "harmonized": "processed", "anomalies": "processed", "baseline": "processed",
}


def stage_file(cfg: dict, region: str, name: str) -> Path:
    return stage_dir(cfg, LAYERS[name], region) / f"{name}.parquet"


def write_stage(cfg: dict, region: str, name: str, df: pd.DataFrame, report: dict | None = None,
                inputs: list[str] | None = None) -> Path:
    out = stage_file(cfg, region, name)
    tmp = out.with_suffix(".parquet.part")
    df.to_parquet(tmp, index=False)
    tmp.replace(out)
    sidecar = {
        "stage": name, "region": region, "rows": len(df), "written_at": dt.datetime.now(dt.UTC).isoformat(),
        "pipeline_version": __version__, "config_hash": config_hash(cfg), "inputs": inputs or [],
    }
    if report is not None:
        sidecar["report"] = report
    out.with_suffix(".json").write_text(json.dumps(sidecar, indent=2, default=str))
    return out


def read_stage(cfg: dict, region: str, name: str) -> pd.DataFrame:
    f = stage_file(cfg, region, name)
    if not f.exists():
        raise FileNotFoundError(f"{f} missing: run the stage that writes {name!r} for region {region!r}")
    return pd.read_parquet(f)


def read_report(cfg: dict, region: str, name: str) -> dict:
    return json.loads(stage_file(cfg, region, name).with_suffix(".json").read_text()).get("report", {})
