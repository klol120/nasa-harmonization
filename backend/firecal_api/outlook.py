"""Burning outlook: one shared machine-learning model that forecasts the next 1-6 months.

Target: VIIRS-equivalent fire-days per 0.05° cell per month (`harmonized`), the same units the website
shows. Region totals are the sum of their cells (as in the exports), so the model forecasts cells and the
region outlook is their sum.

Model: one scikit-learn HistGradientBoostingRegressor (Poisson loss) shared by every country region, with
the region as an input. Inputs are known at the issue month (the last complete month): the cell's
same-month history (last year, 3/5/10-year and all-year means), recent activity and its anomaly, the
region-wide recent anomaly, location, the persistent-source flag, target month and lead time.

Accuracy is measured honestly, on years the model never saw:
  * test:         model fitted on targets up to 2021, scored on 2022-2025 (every month, leads 1-6);
  * confirmation: model fitted up to 2025, scored on 2026 months that are already complete;
  * live:         model fitted on everything complete, forecasting the next six months.
Every score is compared with the baselines a reader would otherwise use: the 5-year same-month mean,
the "typical year" (median of all earlier years) and last year's value.

Reads the export folders directly (duckdb), so it needs no database; `--save` writes the live outlook to
the database through `ml.save_run`, and the API serves it at /regions/{region}/predictions.
"""

from __future__ import annotations

import json
import math
import pickle
import time
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

MODEL_NAME = "outlook-hgb"
MODEL_VERSION = "0.2.0"
HORIZONS = range(1, 7)
MIN_HISTORY = 36  # months of history before the first issue month used for fitting
TEST_YEARS = (2022, 2025)
CELLS_PER_ISSUE = 150  # fitting rows sampled per region, issue month and lead (keeps regions balanced)
SEED = 0

FEATURES = [
    "h", "month", "region", "lat", "lon", "persistent",
    "ly", "m3", "m5", "m10", "mall", "mx5", "fnz", "nb5", "trend",
    "r1", "r3", "r12", "a3", "a12",
    "reg_m5", "reg_ly", "reg_a3", "reg_a12",
]
CATEGORICAL = ["month", "region"]


# ---------------------------------------------------------------- data


@dataclass
class Region:
    name: str
    months: list[str]  # 'YYYY-MM', index = month index
    cells: list[str]  # cell ids, index = cell index
    V: np.ndarray  # (cells, months) float32, NaN where the month is not complete
    ok: np.ndarray  # (months,) bool: month complete (data_available and not partial)
    estimate: np.ndarray  # (months,) bool: MODIS-era value converted to VIIRS-equivalent (is_estimate)
    stats_last_year: int
    lat: np.ndarray
    lon: np.ndarray
    persistent: np.ndarray
    mean: np.ndarray  # (months,) mean over cells, NaN where the month is not complete

    def idx(self, ym: str) -> int:
        return self.months.index(ym)

    @property
    def last_ok(self) -> int:
        return int(np.flatnonzero(self.ok)[-1])

    def year(self, j: int) -> int:
        return int(self.months[j][:4])


def _month_list(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def load_region(folder: Path) -> Region:
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    t = meta["time"]
    months = _month_list(t["first_month"], t["last_month"])
    flags = {x["ym"]: x for x in json.loads((folder / "region_monthly.json").read_text(encoding="utf-8"))}
    ok = np.array([bool(flags.get(ym, {}).get("data_available")) and not flags.get(ym, {}).get("partial_month")
                   for ym in months])

    feats = json.loads((folder / "cells.geojson").read_text(encoding="utf-8"))["features"]
    props = sorted((f["properties"] for f in feats), key=lambda p: p["cell_id"])
    cells = [p["cell_id"] for p in props]
    pos = {c: i for i, c in enumerate(cells)}

    con = duckdb.connect()
    rows = con.execute(
        "select cell_id, ym, harmonized from read_parquet(?)", [str(folder / "calendar.parquet")]
    ).fetchall()
    con.close()
    mpos = {ym: j for j, ym in enumerate(months)}
    V = np.full((len(cells), len(months)), np.nan, dtype=np.float32)
    for cid, ym, v in rows:
        if v is not None and cid in pos and ym in mpos:
            V[pos[cid], mpos[ym]] = v
    V[:, ~ok] = np.nan
    return Region(
        name=meta["region"], months=months, cells=cells, V=V, ok=ok, stats_last_year=t["stats_last_year"],
        estimate=np.array([bool(flags.get(ym, {}).get("is_estimate")) for ym in months]),
        lat=np.array([p["lat_center"] for p in props], dtype=np.float32),
        lon=np.array([p["lon_center"] for p in props], dtype=np.float32),
        persistent=np.array([bool(p.get("is_persistent")) for p in props], dtype=np.float32),
        mean=_nanmean(V, axis=0).astype(np.float32),
    )


def country_regions(export_dir: Path, names: list[str] | None = None) -> list[Path]:
    """Region folders to model. By default every single-country region: multi-country regions such as
    eastmed overlap the country ones, and fitting both would count the same cells twice."""
    out = []
    for p in sorted(export_dir.iterdir()):
        if not (p / "meta.json").is_file():
            continue
        meta = json.loads((p / "meta.json").read_text(encoding="utf-8"))
        if names and meta["region"] not in names:
            continue
        if not names and len(meta.get("countries", [])) != 1:
            continue
        out.append(p)
    return out


# ---------------------------------------------------------------- features


def _nanmean(a: np.ndarray, axis: int = 1) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a, axis=axis)


def _same_month(V: np.ndarray, j: int, years: int | None) -> np.ndarray:
    """V[:, j-12], V[:, j-24], ... (most recent first), up to `years` columns."""
    cols = list(range(j - 12, -1, -12))
    if years is not None:
        cols = cols[:years]
    return V[:, cols] if cols else np.full((V.shape[0], 1), np.nan, dtype=V.dtype)


def _stats(V: np.ndarray, i: int, h: int) -> list[np.ndarray]:
    """History statistics of each row of V, issued after month i, for target month i+h (months <= i only)."""
    j = i + h
    n = V.shape[0]
    S = _same_month(V, j, None)
    ly, m3, m5, m10 = S[:, 0], _nanmean(S[:, :3]), _nanmean(S[:, :5]), _nanmean(S[:, :10])
    mall = _nanmean(S)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mx5 = np.nanmax(S[:, :5], axis=1)
        fnz = np.nanmean(np.where(np.isnan(S), np.nan, S > 0), axis=1)
    nb = [V[:, [c for c in range(j - 12 + d, -1, -12)][:5]] for d in (-1, 1) if j - 12 + d <= i]
    nb5 = _nanmean(np.concatenate(nb, axis=1)) if nb else np.full(n, np.nan)

    r1 = V[:, i]
    r3 = _nanmean(V[:, i - 2:i + 1])
    r12 = _nanmean(V[:, i - 11:i + 1])
    past3 = [V[:, i - 2 - 12 * k:i + 1 - 12 * k] for k in range(1, 6) if i - 2 - 12 * k >= 0]
    past12 = [V[:, i - 11 - 12 * k:i + 1 - 12 * k] for k in range(1, 6) if i - 11 - 12 * k >= 0]
    a3 = r3 - (_nanmean(np.concatenate(past3, axis=1)) if past3 else np.nan)
    a12 = r12 - (_nanmean(np.concatenate(past12, axis=1)) if past12 else np.nan)

    return [ly, m3, m5, m10, mall, mx5, fnz, nb5, m3 - m10, r1, r3, r12, a3, a12]


def features(R: Region, code: int, i: int, h: int, rows: np.ndarray | None = None) -> np.ndarray:
    """Feature matrix for the cells `rows` of R (default: all), issued after month i (complete), for
    target month i+h. Uses only months <= i. Region-wide inputs are the same statistics of the
    region's mean cell."""
    W = R.V if rows is None else R.V[rows]
    n = W.shape[0]
    sel = slice(None) if rows is None else rows
    st = _stats(W, i, h)
    rg = _stats(R.mean[None, :], i, h)
    names = ["ly", "m3", "m5", "m10", "mall", "mx5", "fnz", "nb5", "trend", "r1", "r3", "r12", "a3", "a12"]
    g = {k: np.full(n, v[0], dtype=np.float32) for k, v in zip(names, rg)}
    month = (int(R.months[i][5:]) + h - 1) % 12 + 1
    X = np.column_stack([
        np.full(n, h), np.full(n, month), np.full(n, code), R.lat[sel], R.lon[sel], R.persistent[sel],
        *st, g["m5"], g["ly"], g["a3"], g["a12"],
    ]).astype(np.float32)
    return X


def region_baselines(R: Region, j: int) -> dict[str, float]:
    """Region-total baselines for target month j, from earlier years only."""
    T = np.nansum(R.V, axis=0)
    T[~R.ok] = np.nan
    prev = [T[c] for c in range(j - 12, -1, -12) if np.isfinite(T[c])]
    return {
        "seasonal_5y": float(np.mean(prev[:5])) if prev else math.nan,
        "typical_year": float(np.median(prev)) if prev else math.nan,
        "last_year": float(prev[0]) if prev else math.nan,
    }


# ---------------------------------------------------------------- fitting


def build_training(regions: list[Region], last_target: dict[str, int], rng: np.random.Generator):
    Xs, ys = [], []
    for code, R in enumerate(regions):
        for i in range(MIN_HISTORY, last_target[R.name]):
            if not R.ok[i]:
                continue
            for h in HORIZONS:
                j = i + h
                # Fit only on months VIIRS observed: MODIS-era estimates are much lumpier and pull
                # forecasts up (they still feed the history inputs).
                if j > last_target[R.name] or not R.ok[j] or R.estimate[j]:
                    continue
                take = rng.choice(len(R.cells), size=min(CELLS_PER_ISSUE, len(R.cells)), replace=False)
                y = R.V[take, j]
                keep = np.isfinite(y)
                Xs.append(features(R, code, i, h, take)[keep])
                ys.append(y[keep])
    return np.concatenate(Xs), np.concatenate(ys)


# Candidates compared on the validation years only (fit up to VALIDATION_YEARS[0]-1). "full" knows
# where a cell is and which region it is in; "shared" learns one pattern for every region from the
# history inputs alone, so it also applies to a region added later.
CANDIDATES = {
    "full": [],
    "shared": ["lat", "lon", "region"],
}
# Weight of the 5-year same-month mean in each region's forecast, chosen per region on the validation
# years. 1.0 means the model did not help there: the outlook is the 5-year mean.
BLENDS = (0.0, 0.25, 0.5, 0.75, 1.0)
VALIDATION_YEARS = (2019, 2021)
BAND = (0.1, 0.9)  # likely range: 8 in 10 months


class Outlook:
    """Fitted model + the inputs it uses + its blend with the 5-year same-month mean."""

    def __init__(self, est, cols: list[int], blend: float = 0.0, name: str = ""):
        self.est, self.cols, self.blend, self.name = est, cols, blend, name
        self.n_iter_ = est.n_iter_

    def predict(self, X: np.ndarray) -> np.ndarray:
        p = self.est.predict(X[:, self.cols])
        if self.blend:
            p = (1 - self.blend) * p + self.blend * np.nan_to_num(X[:, FEATURES.index("m5")])
        return p

    def with_blend(self, blend: float) -> "Outlook":
        return Outlook(self.est, self.cols, blend, self.name)


def fit(regions: list[Region], last_target: dict[str, int], candidate: str = "full", blend: float = 0.0):
    from sklearn.ensemble import HistGradientBoostingRegressor

    X, y = build_training(regions, last_target, np.random.default_rng(SEED))
    cols = [k for k, f in enumerate(FEATURES) if f not in CANDIDATES[candidate]]
    cat = [cols.index(FEATURES.index(c)) for c in CATEGORICAL if FEATURES.index(c) in cols]
    est = HistGradientBoostingRegressor(
        loss="poisson", learning_rate=0.05, max_iter=500, max_leaf_nodes=31, min_samples_leaf=200,
        l2_regularization=1.0, categorical_features=cat or None,
        early_stopping=True, validation_fraction=0.1, n_iter_no_change=30, random_state=SEED,
    )
    est.fit(X[:, cols], y)
    return Outlook(est, cols, blend, candidate), len(y)


# ---------------------------------------------------------------- scoring


def score(model, regions: list[Region], targets: dict[str, list[int]]) -> dict:
    """Score every (target month, lead) pair with the model alone ("raw"). Blends with the 5-year mean are
    applied afterwards (`blended`): at region level that is exact, because the region's 5-year mean is the
    sum of its cells' 5-year means."""
    out = {}
    for code, R in enumerate(regions):
        recs = []
        for j in targets[R.name]:
            for h in HORIZONS:
                i = j - h
                if i < MIN_HISTORY or not R.ok[i] or not R.ok[j]:
                    continue
                p = model.predict(features(R, code, i, h))
                recs.append({"h": h, "ym": R.months[j], "actual": float(np.nansum(R.V[:, j])), "raw": float(p.sum()),
                             **region_baselines(R, j)})
        out[R.name] = recs
    return out


def blended(rows: list[dict], w: float) -> list[dict]:
    """Rows with "model" = (1-w) * model + w * 5-year mean (the model alone where the mean is missing)."""
    out = []
    for r in rows:
        b = r["seasonal_5y"]
        m = r["raw"] if not math.isfinite(b) else (1 - w) * r["raw"] + w * b
        out.append({**r, "model": m})
    return out


def summarize(rows: list[dict]) -> dict:
    """Region-level errors. WAPE = sum|forecast-actual| / sum(actual); skill = 1 - MAE/MAE(baseline)."""
    if not rows:
        return {}
    act = np.array([r["actual"] for r in rows])
    res = {"n": len(rows), "actual_mean": float(act.mean())}
    for k in ("model", "seasonal_5y", "typical_year", "last_year"):
        f = np.array([r[k] for r in rows])
        m = np.isfinite(f)
        mae = float(np.abs(f[m] - act[m]).mean())
        res[k] = {"mae": mae, "wape": float(np.abs(f[m] - act[m]).sum() / max(act[m].sum(), 1e-9))}
    for k in ("seasonal_5y", "typical_year", "last_year"):
        res[f"skill_vs_{k}"] = 1 - res["model"]["mae"] / res[k]["mae"] if res[k]["mae"] else math.nan
    best = min(("seasonal_5y", "typical_year", "last_year"), key=lambda k: res[k]["mae"])
    res["best_baseline"] = best
    res["skill_vs_best"] = res[f"skill_vs_{best}"]
    res["beats_baselines"] = res["skill_vs_best"] > 0
    # How often the forecast lands within ±25% of the actual (or ±5 fire-days for quiet months).
    f = np.array([r["model"] for r in rows])
    res["within_25pct"] = float(np.mean(np.abs(f - act) <= np.maximum(0.25 * act, 5)))
    res["bias"] = float(f.mean() / max(act.mean(), 1e-9) - 1)  # + = forecasts too high on average
    return res


def band_quantiles(rows: list[dict]) -> tuple[float, float]:
    """BAND quantiles of log((actual+1)/(forecast+1)): how far real months fell from the forecast."""
    r = np.array([math.log((x["actual"] + 1) / (x["model"] + 1)) for x in rows])
    return (float(np.quantile(r, BAND[0])), float(np.quantile(r, BAND[1]))) if len(r) else (0.0, 0.0)


def coverage(rows: list[dict], q: tuple[float, float]) -> float | None:
    """Share of months whose actual value fell inside the likely range."""
    if not rows:
        return None
    hits = []
    for r in rows:
        lo, hi = _band(r["model"], q)
        hits.append(lo <= r["actual"] <= hi)
    return float(np.mean(hits))


def _band(p: float, q: tuple[float, float]) -> tuple[float, float]:
    return max(0.0, (p + 1) * math.exp(q[0]) - 1), (p + 1) * math.exp(q[1]) - 1


def _rel(rows: list[dict]) -> float:
    s = summarize(rows)
    return s["model"]["mae"] / s["seasonal_5y"]["mae"] if s and s["seasonal_5y"]["mae"] else math.inf


def select(regions: list[Region], log=print) -> dict:
    """On the validation years only: pick the shared candidate, then each region's blend weight and likely
    range. The test years are never used for any choice."""
    last = {R.name: max(j for j in range(len(R.months)) if R.year(j) < VALIDATION_YEARS[0] and R.ok[j]) for R in regions}
    val = {R.name: [j for j in range(len(R.months)) if VALIDATION_YEARS[0] <= R.year(j) <= VALIDATION_YEARS[1] and R.ok[j]]
           for R in regions}
    best = None
    table = []
    for cand in CANDIDATES:
        m, _ = fit(regions, last, cand)
        scored = score(m, regions, val)
        per = {}
        for name, rows in scored.items():
            errs = {w: _rel(blended(rows, w)) for w in BLENDS}
            w = min(errs, key=errs.get)
            per[name] = {"blend": w, "relative_error": errs[w], "by_blend": {str(k): v for k, v in errs.items()}}
        mean_err = float(np.mean([v["relative_error"] for v in per.values()]))
        table.append({"candidate": cand, "mean_relative_error": mean_err, "regions": per})
        log(f"  validation {VALIDATION_YEARS[0]}-{VALIDATION_YEARS[1]}: {cand:6} -> {100 * mean_err:.0f}% of the 5-year mean's "
            "error with per-region blends: " + ", ".join(f"{k} {v['blend']:.2f}" for k, v in per.items()))
        if best is None or mean_err < best[0]:
            best = (mean_err, cand, per, scored)
    _, cand, per, scored = best
    blends = {k: v["blend"] for k, v in per.items()}
    bands = {k: band_quantiles(blended(scored[k], blends[k])) for k in scored}
    return {"candidate": cand, "blends": blends, "bands": bands, "table": table,
            "validation_years": list(VALIDATION_YEARS)}


# ---------------------------------------------------------------- whole run


def method_text(w: float) -> str:
    if w >= 1:
        return "5-year average (the model did not beat it on 2019-2021)"
    if w <= 0:
        return "machine-learning model"
    return f"machine-learning model {100 * (1 - w):.0f}% + 5-year average {100 * w:.0f}%"


def run(export_dir: Path, out_dir: Path, names: list[str] | None = None, log=print) -> dict:
    t0 = time.time()
    regions = [load_region(p) for p in country_regions(export_dir, names)]
    log(f"loaded {len(regions)} regions: " + ", ".join(f"{R.name} ({len(R.cells)} cells)" for R in regions))

    def months_in(R, y0, y1):
        return [j for j, ym in enumerate(R.months) if y0 <= int(ym[:4]) <= y1 and R.ok[j]]

    # 0) choose the inputs, each region's blend and its likely range on the validation years
    sel = select(regions, log)
    cand, blends, bands = sel["candidate"], sel["blends"], sel["bands"]
    log(f"selected: {cand} ({time.time() - t0:.0f}s)")

    # 1) test: fit on targets up to the year before the test, score the test years once
    last_fit = {R.name: max(j for j in range(len(R.months)) if R.year(j) < TEST_YEARS[0] and R.ok[j]) for R in regions}
    m_test, n_fit = fit(regions, last_fit, cand)
    log(f"test model: {n_fit:,} rows, {m_test.n_iter_} trees ({time.time() - t0:.0f}s)")
    test = score(m_test, regions, {R.name: months_in(R, *TEST_YEARS) for R in regions})

    # 2) confirmation: fit up to stats_last_year, score the complete months after it (never seen)
    last_fit = {R.name: max(j for j in range(len(R.months)) if R.year(j) <= R.stats_last_year and R.ok[j]) for R in regions}
    m_conf, n_conf = fit(regions, last_fit, cand)
    log(f"confirmation model: {n_conf:,} rows, {m_conf.n_iter_} trees ({time.time() - t0:.0f}s)")
    conf = score(m_conf, regions, {R.name: [j for j in range(last_fit[R.name] + 1, len(R.months)) if R.ok[j]]
                                   for R in regions})

    # 3) live: fit on every complete month, forecast the next six from the last complete one
    m_live, n_live = fit(regions, {R.name: R.last_ok for R in regions}, cand)
    log(f"live model: {n_live:,} rows, {m_live.n_iter_} trees ({time.time() - t0:.0f}s)")

    test_b = {k: blended(v, blends[k]) for k, v in test.items()}
    conf_b = {k: blended(v, blends[k]) for k, v in conf.items()}
    all_test = [r for v in test_b.values() for r in v]
    report = {
        "model_name": MODEL_NAME, "model_version": MODEL_VERSION, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_complete_month": {R.name: R.months[R.last_ok] for R in regions},
        "target": "harmonized (VIIRS-equivalent fire-days per cell per month); region = sum of cells",
        "features": [FEATURES[k] for k in m_live.cols], "horizons": list(HORIZONS), "test_years": list(TEST_YEARS),
        "selection": sel,
        "fit_rows": {"test": n_fit, "confirmation": n_conf, "live": n_live},
        "test": {"all": summarize(all_test), "by_horizon": {}, "regions": {}},
        "confirmation": {"all": summarize([r for v in conf_b.values() for r in v]), "regions": {}},
        "live": {},
    }
    for h in HORIZONS:
        report["test"]["by_horizon"][str(h)] = summarize([r for r in all_test if r["h"] == h])
    for R in regions:
        k = R.name
        raw = summarize(blended(test[k], 0.0))
        report["test"]["regions"][k] = {
            **summarize(test_b[k]), "blend": blends[k], "method": method_text(blends[k]),
            "model_only_wape": raw.get("model", {}).get("wape"), "interval_coverage": coverage(test_b[k], bands[k]),
        }
        report["confirmation"]["regions"][k] = {
            **summarize(conf_b[k]), "months": sorted({r["ym"] for r in conf_b[k]}),
            "interval_coverage": coverage(conf_b[k], bands[k]),
        }

    live = {}
    for code, R in enumerate(regions):
        i = R.last_ok
        y, mo = map(int, R.months[i].split("-"))
        mdl = m_live.with_blend(blends[R.name])
        months, cells = [], []
        for h in HORIZONS:
            p = mdl.predict(features(R, code, i, h))
            mm = mo + h
            ym = f"{y + (mm - 1) // 12:04d}-{(mm - 1) % 12 + 1:02d}"
            lo, hi = _band(float(p.sum()), bands[R.name])
            months.append({"ym": ym, "h": h, "value": float(p.sum()), "value_low": lo, "value_high": hi})
            cells.append((ym, p))
        live[R.name] = {"issued_after": R.months[i], "months": months, "_cells": cells, "_cell_ids": R.cells}
        report["live"][R.name] = {"issued_after": R.months[i], "months": months}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outlook-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with open(out_dir / "outlook-model.pkl", "wb") as f:
        pickle.dump({"model": m_live, "features": FEATURES, "regions": [R.name for R in regions],
                     "blends": blends, "bands": bands, "version": MODEL_VERSION}, f)
    log(f"done in {time.time() - t0:.0f}s -> {out_dir}")
    return {"report": report, "live": live}


def print_summary(report: dict, log=print) -> None:
    def pct(x):
        return "  n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:+5.0f}%"

    s = report["selection"]
    log(f"\nmodel: {s['candidate']} inputs; each region's blend with the 5-year mean and its likely range chosen on "
        f"{s['validation_years'][0]}-{s['validation_years'][1]}")
    log("err = |forecast - actual| summed / actual summed (lower is better); skill = error saved vs the best "
        "simple baseline;\n±25% = months within 25% (or 5 fire-days); band = share of months inside the 80% range")
    log("\nTEST 2022-2025 (region monthly totals, leads 1-6 months)")
    log(f"{'region':10} {'avg/mo':>7} {'blend':>5} {'err':>5} {'5y':>5} {'typ':>5} {'LY':>5} {'skill':>7} {'±25%':>5} {'band':>5}")
    for name, r in list(report["test"]["regions"].items()) + [("ALL", report["test"]["all"])]:
        cov = r.get("interval_coverage")
        log(f"{name:10} {r['actual_mean']:7.0f} {r.get('blend', float('nan')):5.2f} {100 * r['model']['wape']:4.0f}% "
            f"{100 * r['seasonal_5y']['wape']:4.0f}% {100 * r['typical_year']['wape']:4.0f}% {100 * r['last_year']['wape']:4.0f}% "
            f"{pct(r['skill_vs_best']):>7} {100 * r['within_25pct']:4.0f}% " + (f"{100 * cov:4.0f}%" if cov is not None else "     "))
    log("\nby lead time (all regions):  " + "  ".join(
        f"{h}m err {100 * r['model']['wape']:.0f}% (5y {100 * r['seasonal_5y']['wape']:.0f}%)"
        for h, r in report["test"]["by_horizon"].items()))
    log("\nCONFIRMATION on new 2026 months (never used in fitting or choices)")
    for name, r in list(report["confirmation"]["regions"].items()) + [("ALL", report["confirmation"]["all"])]:
        if not r or "model" not in r:
            continue
        cov = r.get("interval_coverage")
        log(f"{name:10} err {100 * r['model']['wape']:4.0f}%  5y {100 * r['seasonal_5y']['wape']:4.0f}%  "
            f"skill {pct(r['skill_vs_best'])}" + (f"  band {100 * cov:.0f}%" if cov is not None else ""))


async def save(live: dict, report: dict, database_url: str, artifact_uri: str | None = None, log=print) -> None:
    """Write the live outlook of every region as a model run (against its current release)."""
    from . import ml
    from .db import connect

    conn = await connect(database_url)
    try:
        for name, L in live.items():
            rel = await conn.fetchrow("select release_id from release where region_id = $1 and is_current", name)
            if not rel:
                log(f"{name}: no current release in the database, skipped")
                continue
            cell_rows = [(cid, ym, float(v), None, None)
                         for ym, p in L["_cells"] for cid, v in zip(L["_cell_ids"], p) if v >= 0.005]
            t = report["test"]["regions"].get(name) or {}
            metrics = {"test": t, "confirmation": report["confirmation"]["regions"].get(name),
                       "issued_after": L["issued_after"], "method": t.get("method"), "blend": t.get("blend")}
            run_id = await ml.save_run(
                conn, region=name, model_name=MODEL_NAME, model_version=MODEL_VERSION, release_id=rel["release_id"],
                region_predictions=[(m["ym"], m["value"], m["value_low"], m["value_high"]) for m in L["months"]],
                cell_predictions=cell_rows,
                params={"features": report["features"], "horizons": list(HORIZONS),
                        "candidate": report["selection"]["candidate"], "blend": t.get("blend")},
                metrics=metrics, artifact_uri=artifact_uri,
                notes="Shared gradient-boosting outlook blended per region with the 5-year mean; region = sum of "
                      "cells; likely range = 10-90% of 2019-2021 errors.",
            )
            log(f"{name}: saved run {run_id} on release {rel['release_id']} ({len(L['months'])} months, {len(cell_rows)} cell values)")
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> int:
    import argparse
    import asyncio
    import os

    from .config import BACKEND_DIR

    p = argparse.ArgumentParser(prog="python -m firecal_api.outlook", description=__doc__.split("\n")[0])
    p.add_argument("--export-dir", default=os.environ.get("EXPORT_DIR", "../pipeline/data/export"))
    p.add_argument("--out", default="ml-output", help="report and model file folder (default: backend/ml-output)")
    p.add_argument("--regions", nargs="*", help="default: every single-country region")
    p.add_argument("--save", action="store_true", help="also write the live outlook to the database (DATABASE_URL)")
    a = p.parse_args(argv)
    export_dir = Path(a.export_dir)
    if not export_dir.is_absolute():
        export_dir = (BACKEND_DIR / export_dir).resolve()
    out = Path(a.out) if Path(a.out).is_absolute() else BACKEND_DIR / a.out
    res = run(export_dir, out, a.regions)
    print_summary(res["report"])
    if a.save:
        from .config import settings

        asyncio.run(save(res["live"], res["report"], settings().database_url, str(out / "outlook-model.pkl")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
