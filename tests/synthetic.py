"""Synthetic FIRMS-shaped CSVs with a known true VIIRS/MODIS ratio. Used only in tests.

Model, per 0.05° cell and UTC day:
  a fire burns with probability q[m];
  given a fire, Terra detects with p_terra[m], Aqua with p_aqua[m], S-NPP with p_viirs[m], independently;
  a VIIRS detection is a cluster of 1 + Poisson(viirs_cluster) pixels inside the cell
  (so detections over-count and fire-days must collapse them).
Terra only before terra_only_until; VIIRS only from viirs_start.

Truth in fire-days (expected values, exact in the large-sample limit):
  a[m]  = p_viirs / (1 - (1 - p_terra)(1 - p_aqua))     VIIRS / MODIS(Terra ∪ Aqua)
  kT[m] = (1 - (1 - p_terra)(1 - p_aqua)) / p_terra     MODIS(T ∪ A) / Terra
Noise rows cleaning must remove: type 2 static sources and low-confidence detections.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

MODIS_COLS = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time", "satellite",
              "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type", "country"]
VIIRS_COLS = ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time", "satellite",
              "instrument", "confidence", "version", "bright_ti5", "frp", "daynight", "type", "country"]


@dataclass
class SynthSpec:
    seed: int = 0
    start: dt.date = dt.date(2000, 11, 1)
    end: dt.date = dt.date(2020, 12, 31)
    origin_lat: float = 10.0          # SW corner of the cell block (on a 0.05° boundary)
    origin_lon: float = 20.0
    n_rows: int = 6
    n_cols: int = 6
    size: float = 0.05
    q: np.ndarray = field(default_factory=lambda: np.array([.02, .02, .03, .04, .05, .08, .12, .14, .10, .06, .03, .02]))
    p_terra: np.ndarray = field(default_factory=lambda: np.full(12, 0.30))
    p_aqua: np.ndarray = field(default_factory=lambda: np.full(12, 0.35))
    p_viirs: np.ndarray = field(default_factory=lambda: np.linspace(0.95, 0.70, 12))
    viirs_cluster: float = 1.5
    terra_only_until: dt.date = dt.date(2002, 7, 4)
    viirs_start: dt.date = dt.date(2012, 1, 20)
    noise_static_per_year: int = 40
    noise_low_conf_frac: float = 0.1
    country: str = "Synthland"

    @property
    def bbox(self):
        return [self.origin_lon, self.origin_lat, self.origin_lon + self.n_cols * self.size,
                self.origin_lat + self.n_rows * self.size]

    def truth(self) -> dict:
        pm = 1 - (1 - self.p_terra) * (1 - self.p_aqua)
        return {"a": self.p_viirs / pm, "kT": pm / self.p_terra}


def _jitter(rng, n, centre, half):
    return centre + rng.uniform(-half, half, n)


def simulate(spec: SynthSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (modis, viirs) detection frames in FIRMS archive layout plus a `_noise` marker column."""
    rng = np.random.default_rng(spec.seed)
    days = pd.date_range(spec.start, spec.end)
    month = days.month.values - 1
    n_cells = spec.n_rows * spec.n_cols
    r, c = np.divmod(np.arange(n_cells), spec.n_cols)
    lat_c = spec.origin_lat + (r + 0.5) * spec.size
    lon_c = spec.origin_lon + (c + 0.5) * spec.size
    fire = rng.random((len(days), n_cells)) < spec.q[month][:, None]
    d_idx, c_idx = np.nonzero(fire)
    m = month[d_idx]
    date = days[d_idx]
    aqua_on = np.asarray(date >= pd.Timestamp(spec.terra_only_until))
    viirs_on = np.asarray(date >= pd.Timestamp(spec.viirs_start))

    modis_rows = []
    for sat, p, on, hhmm in [("Terra", spec.p_terra, np.ones_like(aqua_on), "0830"),
                             ("Aqua", spec.p_aqua, aqua_on, "1130")]:
        hit = on & (rng.random(len(d_idx)) < p[m])
        k = hit.sum()
        modis_rows.append(pd.DataFrame({
            "latitude": _jitter(rng, k, lat_c[c_idx[hit]], 0.015).round(4),
            "longitude": _jitter(rng, k, lon_c[c_idx[hit]], 0.015).round(4),
            "brightness": 320.0, "scan": 1.0, "track": 1.0, "acq_date": date[hit].strftime("%Y-%m-%d"),
            "acq_time": hhmm, "satellite": sat, "instrument": "MODIS",
            "confidence": rng.integers(30, 101, k), "version": "6.03", "bright_t31": 300.0,
            "frp": rng.gamma(2, 10, k).round(1), "daynight": "D", "type": 0, "country": spec.country}))
    modis = pd.concat(modis_rows, ignore_index=True)

    hit = viirs_on & (rng.random(len(d_idx)) < spec.p_viirs[m])
    reps = 1 + rng.poisson(spec.viirs_cluster, hit.sum())
    vc = np.repeat(c_idx[hit], reps)
    vdate = np.repeat(np.asarray(date[hit].strftime("%Y-%m-%d")), reps)
    k = len(vc)
    viirs = pd.DataFrame({
        "latitude": _jitter(rng, k, lat_c[vc], 0.015).round(5),
        "longitude": _jitter(rng, k, lon_c[vc], 0.015).round(5),
        "bright_ti4": 330.0, "scan": 0.4, "track": 0.4, "acq_date": vdate, "acq_time": "1110",
        "satellite": "N", "instrument": "VIIRS", "confidence": rng.choice(["n", "h"], k), "version": "2",
        "bright_ti5": 295.0, "frp": rng.gamma(2, 3, k).round(2), "daynight": "D", "type": 0,
        "country": spec.country})

    n_years = spec.end.year - spec.start.year + 1
    modis = _add_noise(rng, spec, modis, low_value=10, n_static=spec.noise_static_per_year * n_years)
    viirs = _add_noise(rng, spec, viirs, low_value="l", n_static=spec.noise_static_per_year * n_years)
    return modis, viirs


def _add_noise(rng, spec, frame: pd.DataFrame, low_value, n_static: int) -> pd.DataFrame:
    """Append rows cleaning must drop: type-2 static sources and low-confidence copies.

    Noise rows get a distinct acq_time so they never duplicate a real detection."""
    seed = lambda: int(rng.integers(1 << 31))  # noqa: E731
    static = frame.sample(n_static, replace=True, random_state=seed()).assign(type=2, daynight="N", acq_time="2200")
    low = frame.sample(frac=spec.noise_low_conf_frac, random_state=seed()).assign(confidence=low_value, acq_time="2300")
    return pd.concat([frame.assign(_noise=False), static.assign(_noise=True), low.assign(_noise=True)],
                     ignore_index=True)


def write_csvs(spec: SynthSpec, out_dir: Path, region: str = "synth") -> dict:
    """Write {out_dir}/{region}/{MODIS_SP|VIIRS_SNPP_SP}_{year}.csv like the Phase 0 region files."""
    modis, viirs = simulate(spec)
    d = Path(out_dir) / region
    d.mkdir(parents=True, exist_ok=True)
    files = []
    for name, df in (("MODIS_SP", modis), ("VIIRS_SNPP_SP", viirs)):
        for y, g in df.groupby(df.acq_date.str[:4]):
            f = d / f"{name}_{y}.csv"
            cols = MODIS_COLS if name == "MODIS_SP" else VIIRS_COLS
            g.sort_values(["acq_date", "acq_time"])[cols].to_csv(f, index=False)
            files.append(f)
    return {"files": files, "modis": modis, "viirs": viirs, "truth": spec.truth()}


def config_overrides(spec: SynthSpec, tmp: Path, region: str = "synth") -> dict:
    """Config overrides pointing the pipeline at synthetic data in tmp."""
    return {
        "paths": {"raw": str(tmp / "raw"), "interim": str(tmp / "interim"), "processed": str(tmp / "processed"),
                  "export": str(tmp / "export"), "reports": str(tmp / "reports")},
        "regions": {region: {"bbox": spec.bbox, "countries": [spec.country]}},
        "inputs": [
            {"path": "{raw}/{region}/MODIS_SP_[0-9][0-9][0-9][0-9].csv", "format": "firms_archive_csv", "source": "MODIS_SP"},
            {"path": "{raw}/{region}/VIIRS_SNPP_SP_[0-9][0-9][0-9][0-9].csv", "format": "firms_archive_csv", "source": "VIIRS_SNPP_SP"},
        ],
        "coverage": {"MODIS_SP": [spec.start, spec.end], "VIIRS_SNPP_SP": [spec.viirs_start, spec.end]},
        "gaps": {"reference_regions": [region], "known": []},
        "persistence": {"diagnostic_regions": []},
    }
