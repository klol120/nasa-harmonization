"""Load config.yaml and resolve per-region stage paths."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.yaml"

REQUIRED = ["paths", "regions", "inputs", "coverage", "grid", "sensors", "clean", "persistence", "gaps"]


class ConfigError(ValueError):
    pass


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    path = Path(path) if path else DEFAULT_CONFIG
    cfg = yaml.safe_load(path.read_text())
    if overrides:
        cfg = deep_merge(cfg, overrides)
    cfg["_root"] = str(path.resolve().parent)
    validate(cfg)
    return cfg


def deep_merge(base: dict, extra: dict) -> dict:
    """Recursive merge; a key ending in "!" replaces instead of merging (e.g. {"donors!": {}})."""
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if k.endswith("!"):
            out[k[:-1]] = copy.deepcopy(v)
        else:
            out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def validate(cfg: dict) -> None:
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise ConfigError(f"config missing sections: {missing}")
    for name, r in cfg["regions"].items():
        w, s, e, n = r["bbox"]
        if not (w < e and s < n):
            raise ConfigError(f"region {name}: bbox must be west,south,east,north")
        if not r.get("countries"):
            raise ConfigError(f"region {name}: countries is empty")
    for src, (a, b) in cfg["coverage"].items():
        if as_date(a) > as_date(b):
            raise ConfigError(f"coverage {src}: start after end")
    c = cfg["sensors"].get("continuation")
    if c and c["satellite"] not in cfg["sensors"]["satellites"]:
        raise ConfigError(f"sensors.continuation.satellite {c['satellite']} is not in sensors.satellites")
    mode = cfg["persistence"]["mode"]
    if mode not in ("auto", "always", "off"):
        raise ConfigError(f"persistence.mode must be auto|always|off, got {mode}")


def as_date(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def path(cfg: dict, key: str) -> Path:
    p = Path(cfg["paths"][key])
    return p if p.is_absolute() else Path(cfg["_root"]) / p


def region(cfg: dict, name: str) -> dict:
    if name not in cfg["regions"]:
        raise ConfigError(f"unknown region {name!r}; known: {list(cfg['regions'])}")
    return cfg["regions"][name]


def stage_dir(cfg: dict, layer: str, region_name: str) -> Path:
    d = path(cfg, layer) / region_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_hash(cfg: dict) -> str:
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    blob = json.dumps(clean, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:16]


def region_settings(cfg: dict, section: str, region_name: str) -> dict:
    """A config section with its `by_region.<region>` overrides applied (by_region itself removed)."""
    sec = {k: v for k, v in cfg[section].items() if k != "by_region"}
    return deep_merge(sec, (cfg[section].get("by_region") or {}).get(region_name, {}))


def continuation(cfg: dict) -> dict | None:
    """sensors.continuation with switch_date as a date, or None when the continuation satellite has no
    configured coverage (e.g. test configs). The switch is the first day served by the continuation."""
    from .outages import satellite_coverage

    c = cfg["sensors"].get("continuation")
    if not c or c["satellite"] not in satellite_coverage(cfg):
        return None
    return {**c, "switch_date": as_date(c["switch_date"])}
