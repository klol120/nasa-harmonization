"""Burning outlook: one shared machine-learning model that forecasts the next 1-6 months.

Target: VIIRS-equivalent fire-days per 0.05° cell per month (`harmonized`), the same units the website
shows. Region totals are the sum of their cells (as in the exports), so the model forecasts cells and the
region outlook is their sum.

Model: one scikit-learn HistGradientBoostingRegressor (Poisson loss) shared by every country region, with
the region as an optional input. Features use complete VIIRS-era history available by the issue
month: seasonality, recent activity and anomalies, location, target month and lead time.

The 2019–2021 split selects the model recipe. Forecasts for 2022–2023 pick the published method and
fit its intervals. The later 2024–2025 evaluation and the recent check use the frozen method.
Every scored issue is at or after the last month the model was fitted on. These checks use the
current export, which may contain retrospective revisions to the satellite record.

Reads the export folders directly (duckdb), so it needs no database; `--save` writes the live outlook to
the database through `ml.save_run`, and the API serves it at /regions/{region}/predictions.
"""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np

from .ingest import export_fingerprint

MODEL_NAME = "outlook-hgb"
MODEL_VERSION = "0.3.0"
HORIZONS = range(1, 7)
MIN_HISTORY = 36  # months of history before the first issue month used for fitting
METHOD_YEARS = (2022, 2023)
TEST_YEARS = (2024, 2025)
CELLS_PER_ISSUE = 150  # fitting rows sampled per region, issue month and lead (keeps regions balanced)
SEED = 0

FEATURES = [
    "h", "month", "region", "lat", "lon",
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
    lat: np.ndarray
    lon: np.ndarray
    mean: np.ndarray  # (months,) mean over cells, NaN where the month is not complete
    fingerprint: str = ""

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
    fingerprint = export_fingerprint(folder, "calendar.parquet")
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
    estimate = np.array([bool(flags.get(ym, {}).get("is_estimate")) for ym in months])
    # The MODIS-to-VIIRS factors used by the current export were fitted retrospectively.
    # Use observations for both predictors and targets in the issue-date backtest.
    ok &= ~estimate
    V[:, ~ok] = np.nan
    if fingerprint != export_fingerprint(folder, "calendar.parquet"):
        raise ValueError(f"{folder}: export changed while loading the outlook")
    return Region(
        name=meta["region"], months=months, cells=cells, V=V, ok=ok,
        lat=np.array([p["lat_center"] for p in props], dtype=np.float32),
        lon=np.array([p["lon_center"] for p in props], dtype=np.float32),
        mean=_nanmean(V, axis=0).astype(np.float32),
        fingerprint=fingerprint,
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
        np.full(n, h), np.full(n, month), np.full(n, code), R.lat[sel], R.lon[sel],
        *st, g["m5"], g["ly"], g["a3"], g["a12"],
    ]).astype(np.float32)
    return X


def region_baselines(totals: np.ndarray, j: int, issue: int) -> dict[str, float]:
    """Region-total baselines for target month j, using observations available by the issue."""
    prev = [totals[c] for c in range(j - 12, -1, -12) if c <= issue and np.isfinite(totals[c])]
    last_year = j - 12
    return {
        "seasonal_5y": float(np.mean(prev[:5])) if prev else math.nan,
        "typical_year": float(np.median(prev)) if prev else math.nan,
        "last_year": float(totals[last_year]) if 0 <= last_year <= issue else math.nan,
    }


def observed_totals(region: Region) -> np.ndarray:
    return np.where(region.ok, np.nansum(region.V, axis=0, dtype=np.float64), np.nan)


# ---------------------------------------------------------------- fitting


def build_training(regions: list[Region], last_target: dict[str, int], rng: np.random.Generator):
    Xs, ys = [], []
    for code, R in enumerate(regions):
        for i in range(MIN_HISTORY, last_target[R.name]):
            if not R.ok[i]:
                continue
            for h in HORIZONS:
                j = i + h
                # Fit only on observed VIIRS months.
                if j > last_target[R.name] or not R.ok[j]:
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
BASELINES = ("seasonal_5y", "typical_year", "last_year")
BASELINE_NAMES = {"seasonal_5y": "5-year same-month average", "typical_year": "historical same-month median",
                  "last_year": "last year's same month"}


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


def score(model, regions: list[Region], targets: dict[str, list[int]], *, fitted_through: str) -> dict:
    """Score only issues after all of the shared model's training targets were available."""
    out = {}
    for code, R in enumerate(regions):
        recs = []
        totals = observed_totals(R)
        for j in targets[R.name]:
            for h in HORIZONS:
                i = j - h
                if i < MIN_HISTORY or not R.ok[i] or not R.ok[j]:
                    continue
                if R.months[i] < fitted_through:
                    continue
                baselines = region_baselines(totals, j, i)
                if not all(math.isfinite(v) for v in baselines.values()):
                    continue
                p = model.predict(features(R, code, i, h))
                recs.append({"h": h, "ym": R.months[j], "issue": R.months[i], "actual": float(totals[j]),
                             "raw": float(p.sum(dtype=np.float64)), **baselines})
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


def published_rows(rows: list[dict], method: str) -> list[dict]:
    if method == "outlook":
        return rows
    return [{**r, "model": r[method]} for r in rows]


def summarize(rows: list[dict]) -> dict:
    """Region-level errors. WAPE = sum|forecast-actual| / sum(actual); skill = 1 - MAE/MAE(baseline)."""
    if not rows:
        return {}
    act = np.array([r["actual"] for r in rows])
    res = {"n": len(rows), "actual_mean": float(act.mean())}
    for k in ("model", *BASELINES):
        f = np.array([r[k] for r in rows])
        m = np.isfinite(f)
        mae = float(np.abs(f[m] - act[m]).mean())
        actual_total = float(act[m].sum())
        res[k] = {"mae": mae, "wape": float(np.abs(f[m] - act[m]).sum() / actual_total) if actual_total else None}
    for k in BASELINES:
        res[f"skill_vs_{k}"] = 1 - res["model"]["mae"] / res[k]["mae"] if res[k]["mae"] else None
    best = min(BASELINES, key=lambda k: res[k]["mae"])
    res["best_baseline"] = best
    res["skill_vs_best"] = res[f"skill_vs_{best}"]
    res["beats_baselines"] = res["model"]["mae"] < res[best]["mae"]
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
    return tuple(max(0.0, (p + 1) * math.exp(x) - 1) for x in q)


def _rel(rows: list[dict]) -> float:
    s = summarize(rows)
    if not s:
        return math.inf
    if s["seasonal_5y"]["mae"] == 0:
        return 1.0 if s["model"]["mae"] == 0 else math.inf
    return s["model"]["mae"] / s["seasonal_5y"]["mae"]


def training_cutoffs(regions: list[Region], through: str) -> dict[str, int]:
    return {R.name: max(j for j, ym in enumerate(R.months) if ym <= through and R.ok[j]) for R in regions}


def select(regions: list[Region], log=print) -> dict:
    """Choose the candidate and blend weights on the validation years."""
    through = f"{VALIDATION_YEARS[0] - 1}-12"
    last = training_cutoffs(regions, through)
    val = {R.name: [j for j in range(len(R.months)) if VALIDATION_YEARS[0] <= R.year(j) <= VALIDATION_YEARS[1] and R.ok[j]]
           for R in regions}
    best = None
    table = []
    for cand in CANDIDATES:
        m, _ = fit(regions, last, cand)
        scored = score(m, regions, val, fitted_through=through)
        per = {}
        for name, rows in scored.items():
            errs = {w: _rel(blended(rows, w)) for w in BLENDS}
            w = min(errs, key=errs.get)
            per[name] = {"blend": w, "relative_error": errs[w] if math.isfinite(errs[w]) else None,
                         "by_blend": {str(k): v if math.isfinite(v) else None for k, v in errs.items()}}
        ratios = [v["relative_error"] for v in per.values() if v["relative_error"] is not None]
        mean_err = float(np.mean(ratios)) if ratios else math.inf
        table.append({"candidate": cand, "mean_relative_error": mean_err if ratios else None, "regions": per})
        log(f"  validation {VALIDATION_YEARS[0]}-{VALIDATION_YEARS[1]}: {cand:6} -> {100 * mean_err:.0f}% of the 5-year mean's "
            "error with per-region blends: " + ", ".join(f"{k} {v['blend']:.2f}" for k, v in per.items()))
        if best is None or mean_err < best[0]:
            best = (mean_err, cand, per)
    _, cand, per = best
    blends = {k: v["blend"] for k, v in per.items()}
    return {"candidate": cand, "blends": blends, "table": table,
            "validation_years": list(VALIDATION_YEARS)}


# ---------------------------------------------------------------- whole run


def method_text(w: float) -> str:
    if w >= 1:
        return "5-year average (the model did not beat it on 2019-2021)"
    if w <= 0:
        return "machine-learning model"
    return f"machine-learning model {100 * (1 - w):.0f}% + 5-year average {100 * w:.0f}%"


def pick_method(rows: list[dict]) -> str:
    scores = summarize(rows)
    if not scores:
        return "seasonal_5y"
    return "outlook" if scores["beats_baselines"] else scores["best_baseline"]


def evaluate(rows: list[dict], method: str, band: tuple[float, float] | None) -> dict:
    published = published_rows(rows, method)
    if not published:
        return {}
    result = summarize(published)
    result.update(
        candidate=summarize(rows)["model"],
        interval_coverage=coverage(published, band) if band is not None else None,
        months=sorted({r["ym"] for r in rows}),
        by_horizon={},
    )
    for h in HORIZONS:
        lead = [r for r in published if r["h"] == h]
        if lead:
            result["by_horizon"][str(h)] = {
                **summarize(lead),
                "interval_coverage": coverage(lead, band) if band is not None else None,
            }
    return result


def run(export_dir: Path, out_dir: Path, names: list[str] | None = None, log=print) -> dict:
    t0 = time.time()
    regions = [load_region(p) for p in country_regions(export_dir, names)]
    if not regions:
        raise ValueError(f"No matching export regions in {export_dir}")
    log(f"loaded {len(regions)} regions: " + ", ".join(f"{R.name} ({len(R.cells)} cells)" for R in regions))

    def months_in(R, y0, y1):
        return [j for j, ym in enumerate(R.months) if y0 <= int(ym[:4]) <= y1 and R.ok[j]]

    # Choose the shared recipe and blend weights before choosing the published method.
    sel = select(regions, log)
    cand, blends = sel["candidate"], sel["blends"]
    log(f"selected: {cand} ({time.time() - t0:.0f}s)")

    historical_cutoff = f"{METHOD_YEARS[0] - 1}-12"
    m_test, n_fit = fit(regions, training_cutoffs(regions, historical_cutoff), cand)
    log(f"test model: {n_fit:,} rows, {m_test.n_iter_} trees ({time.time() - t0:.0f}s)")
    tuning = score(m_test, regions, {R.name: months_in(R, *METHOD_YEARS) for R in regions}, fitted_through=historical_cutoff)
    tuning = {k: blended(v, blends[k]) for k, v in tuning.items()}
    methods = {k: pick_method(v) for k, v in tuning.items()}
    bands = {k: band_quantiles(published_rows(v, methods[k])) if v else None for k, v in tuning.items()}
    test = score(m_test, regions, {R.name: months_in(R, *TEST_YEARS) for R in regions}, fitted_through=historical_cutoff)

    recent_cutoff = f"{TEST_YEARS[-1]}-12"
    m_conf, n_conf = fit(regions, training_cutoffs(regions, recent_cutoff), cand)
    log(f"confirmation model: {n_conf:,} rows, {m_conf.n_iter_} trees ({time.time() - t0:.0f}s)")
    conf = score(m_conf, regions, {R.name: months_in(R, TEST_YEARS[-1] + 1, R.year(R.last_ok))
                                   for R in regions}, fitted_through=recent_cutoff)

    live_cutoff = min(R.months[R.last_ok] for R in regions)
    m_live, n_live = fit(regions, training_cutoffs(regions, live_cutoff), cand)
    log(f"live model: {n_live:,} rows, {m_live.n_iter_} trees ({time.time() - t0:.0f}s)")

    test_b = {k: blended(v, blends[k]) for k, v in test.items()}
    conf_b = {k: blended(v, blends[k]) for k, v in conf.items()}
    all_test = [r for k, rows in test_b.items() for r in published_rows(rows, methods[k])]
    all_conf = [r for k, rows in conf_b.items() for r in published_rows(rows, methods[k])]
    report = {
        "model_name": MODEL_NAME, "model_version": MODEL_VERSION, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "last_complete_month": {R.name: R.months[R.last_ok] for R in regions},
        "export_fingerprints": {R.name: R.fingerprint for R in regions},
        "target": "harmonized (VIIRS-equivalent fire-days per cell per month); region = sum of cells",
        "features": [FEATURES[k] for k in m_live.cols], "horizons": list(HORIZONS), "test_years": list(TEST_YEARS),
        "selection": {**sel, "method_years": list(METHOD_YEARS), "methods": methods},
        "fitted_through": {"test": historical_cutoff, "confirmation": recent_cutoff, "live": live_cutoff},
        "fit_rows": {"test": n_fit, "confirmation": n_conf, "live": n_live},
        "test": {"all": summarize(all_test), "by_horizon": {}, "regions": {}},
        "confirmation": {"all": summarize(all_conf), "regions": {}},
        "method_evaluation": {},
        "live": {},
    }
    for h in HORIZONS:
        report["test"]["by_horizon"][str(h)] = summarize([r for r in all_test if r["h"] == h])
    for R in regions:
        k = R.name
        report["test"]["regions"][k] = evaluate(test_b[k], methods[k], bands[k])
        report["confirmation"]["regions"][k] = evaluate(conf_b[k], methods[k], bands[k])
        report["method_evaluation"][k] = evaluate(tuning[k], methods[k], bands[k])

    live = {}
    for code, R in enumerate(regions):
        i = R.last_ok
        y, mo = map(int, R.months[i].split("-"))
        totals = observed_totals(R)
        method = methods[R.name]
        months, cells = [], []
        for h in HORIZONS:
            X = features(R, code, i, h)
            p = m_live.with_blend(blends[R.name]).predict(X)
            candidate = float(p.sum(dtype=np.float64))
            mm = mo + h
            ym = f"{y + (mm - 1) // 12:04d}-{(mm - 1) % 12 + 1:02d}"
            baseline = region_baselines(totals, i + h, i)
            applied = method
            if method != "outlook" and not math.isfinite(baseline[method]):
                applied = "seasonal_5y" if math.isfinite(baseline["seasonal_5y"]) else "outlook"
            value = candidate if applied == "outlook" else baseline[applied]
            lo, hi = _band(value, bands[R.name]) if bands[R.name] is not None and applied == method else (None, None)
            months.append({"ym": ym, "h": h, "value": value, "value_low": lo, "value_high": hi,
                           "candidate": candidate, "method": applied})
            if applied == "outlook":
                cells.append((ym, p))
        info = {"issued_after": R.months[i], "months": months, "method": method,
                "method_label": method_text(blends[R.name]) if method == "outlook" else BASELINE_NAMES[method]}
        live[R.name] = {**info, "_cells": cells, "_cell_ids": R.cells}
        report["live"][R.name] = info

    out_dir.mkdir(parents=True, exist_ok=True)
    data_key = hashlib.sha256(json.dumps(report["export_fingerprints"], sort_keys=True).encode()).hexdigest()
    artifact = out_dir / f"outlook-{MODEL_VERSION}-{data_key}.pkl"
    with artifact.open("wb") as f:
        pickle.dump({"estimator": m_live.est, "feature_columns": m_live.cols,
                     "features": FEATURES, "regions": [R.name for R in regions],
                     "blends": blends, "bands": bands, "methods": methods, "version": MODEL_VERSION}, f)
    report["artifact"] = artifact.name
    (out_dir / "outlook-report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    log(f"done in {time.time() - t0:.0f}s -> {out_dir}")
    return {"report": report, "live": live, "artifact": artifact}


def print_summary(report: dict, log=print) -> None:
    log("\nRegion       2024–2025 error   Recent error   Published method")
    for name, r in report["live"].items():
        scores = [report[k]["regions"][name].get("model", {}).get("wape") for k in ("test", "confirmation")]
        test, recent = ["—" if x is None else f"{x:.1%}" for x in scores]
        log(f"{name:12} {test:>15} {recent:>14}   {r['method_label']}")


async def already_published(conn, region: str, issue: str) -> bool:
    return await conn.fetchval(
        """select exists (
            select 1 from model_run m join release r using (release_id)
            where r.region_id = $1 and m.model_name = $2 and m.model_version = $3
              and m.metrics->>'issued_after' >= $4)""",
        region, MODEL_NAME, MODEL_VERSION, issue,
    )


async def has_due_exports(folders: list[Path], database_url: str) -> bool:
    from .db import connect

    conn = await connect(database_url)
    try:
        for folder in folders:
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
            flags = json.loads((folder / "region_monthly.json").read_text(encoding="utf-8"))
            issue = max(row["ym"] for row in flags if row["data_available"] and not row["partial_month"] and not row["is_estimate"])
            if not await already_published(conn, meta["region"], issue):
                return True
        return False
    finally:
        await conn.close()


async def save(live: dict, report: dict, database_url: str, artifact_uri: str | None = None, *, if_due=False, log=print) -> None:
    """Publish atomically against the exact current exports used to train the shared model."""
    from . import ml
    from .db import connect

    conn = await connect(database_url)
    try:
        fingerprints = report["export_fingerprints"]
        async with conn.transaction():
            await conn.execute("select pg_advisory_xact_lock(hashtext($1))", MODEL_NAME)
            releases = await conn.fetch(
                """select region_id, release_id, export_fingerprint from release
                   where is_current and region_id = any($1::text[]) order by region_id for share""",
                sorted(fingerprints),
            )
            current = {r["region_id"]: r for r in releases}
            mismatched = [k for k, fp in fingerprints.items() if k not in current or current[k]["export_fingerprint"] != fp]
            if mismatched:
                raise ValueError(f"Outlook exports differ from the current database releases: {', '.join(mismatched)}. "
                                 "Ingest the exact exports before publishing.")
            for name, L in live.items():
                release_id = current[name]["release_id"]
                if if_due and await already_published(conn, name, L["issued_after"]):
                    continue
                if await conn.fetchval(
                    "select exists (select 1 from model_run where release_id = $1 and model_name = $2 and model_version = $3)",
                    release_id, MODEL_NAME, MODEL_VERSION,
                ):
                    continue
                cell_rows = [(cid, ym, float(v), None, None)
                             for ym, p in L["_cells"] for cid, v in zip(L["_cell_ids"], p) if v >= 0.005]
                selection = report["selection"]
                metrics = {
                    "test": report["test"]["regions"][name], "confirmation": report["confirmation"]["regions"][name],
                    "method_evaluation": report["method_evaluation"][name], "test_years": report["test_years"],
                    "method_years": selection["method_years"], "issued_after": L["issued_after"],
                    "method": L["method_label"], "method_kind": L["method"], "blend": selection["blends"][name],
                    "monthly_comparison": {m["ym"]: {"candidate": m["candidate"], "method": m["method"]} for m in L["months"]},
                }
                run_id = await ml.save_run(
                    conn, region=name, model_name=MODEL_NAME, model_version=MODEL_VERSION, release_id=release_id,
                    region_predictions=[(m["ym"], m["value"], m["value_low"], m["value_high"]) for m in L["months"]],
                    cell_predictions=cell_rows,
                    params={"features": report["features"], "horizons": list(HORIZONS),
                            "candidate": selection["candidate"], "export_fingerprints": fingerprints,
                            "fitted_through": report["fitted_through"]["live"]},
                    metrics=metrics, artifact_uri=artifact_uri,
                    notes="Method and prediction ranges selected on issue-date backtests for 2022–2023.",
                )
                log(f"{name}: saved run {run_id} on release {release_id} ({len(L['months'])} months, {len(cell_rows)} cell values)")
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
    p.add_argument("--if-due", action="store_true", help="with --save, run only when an unpublished complete month exists")
    a = p.parse_args(argv)
    if a.if_due and not a.save:
        p.error("--if-due requires --save")
    export_dir = Path(a.export_dir)
    if not export_dir.is_absolute():
        export_dir = (BACKEND_DIR / export_dir).resolve()
    out = Path(a.out) if Path(a.out).is_absolute() else BACKEND_DIR / a.out
    if a.save:
        from .config import settings

        database_url = settings().database_url
        folders = country_regions(export_dir, a.regions)
        if not folders:
            p.error(f"no matching export regions in {export_dir}")
        if a.if_due and not asyncio.run(has_due_exports(folders, database_url)):
            print("All outlooks are already published for their last complete month.")
            return 0
    res = run(export_dir, out, a.regions)
    print_summary(res["report"])
    if a.save:
        asyncio.run(save(res["live"], res["report"], database_url, str(res["artifact"]), if_due=a.if_due))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
