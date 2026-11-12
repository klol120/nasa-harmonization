"""Ratio-of-sums transfer factors (method steps 2-3), strategies, year bootstrap. Pure functions.

A factor maps a denominator count to a numerator count per calendar month:
  a_m  = sum_y N_V / sum_y N_M        (VIIRS from MODIS, step 3)
  kT_m = sum_y N_T∪A / sum_y N_T      (Terra ∪ Aqua from Terra only, step 2)

Counts are YearMonth tables: arrays num[y, m], den[y, m] over a list of years. Every function works
on sums over years with a leading batch axis, so one call evaluates all bootstrap draws.

Strategies:
  single           one factor for all months (local)
  local            per month, local sums
  donor:G          per month, donor group G
  pooled:G         per month, local + donor sums
  blend:G          a_m = (V_L + k a_D) / (M_L + k): local ratio shrunk to the donor ratio with k
                   pseudo-counts; the weight on local is w_m = M_L / (M_L + k). Linear (not log) so
                   months with zero local VIIRS or MODIS are well defined.
A month with a zero denominator falls back to that group's all-month factor.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class YearMonth:
    years: np.ndarray          # (ny,)
    num: np.ndarray            # (ny, 12)
    den: np.ndarray            # (ny, 12)

    def select(self, years) -> "YearMonth":
        m = np.isin(self.years, list(years))
        return YearMonth(self.years[m], self.num[m], self.den[m])

    def sums(self, weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Sums over years; weights (B, ny) give one sum per bootstrap draw."""
        if weights is None:
            return self.num.sum(0), self.den.sum(0)
        return weights @ self.num, weights @ self.den


def year_month_table(fire_days: pd.DataFrame, num_col: str, den_col: str, years) -> YearMonth:
    """Region sums of two fire-day flag columns per (year, month), zero-filled."""
    years = np.asarray(sorted(years))
    d = fire_days[fire_days.date.dt.year.isin(years)]
    g = d.groupby([d.date.dt.year, d.date.dt.month])[[num_col, den_col]].sum()
    idx = pd.MultiIndex.from_product([years, range(1, 13)])
    g = g.reindex(idx, fill_value=0)
    return YearMonth(years, g[num_col].to_numpy(float).reshape(-1, 12), g[den_col].to_numpy(float).reshape(-1, 12))


def _ratio(num, den):
    """Per-month ratio, falling back to the all-month ratio where den == 0."""
    num, den = np.atleast_2d(num), np.atleast_2d(den)
    tot = num.sum(-1, keepdims=True) / np.where(den.sum(-1, keepdims=True) > 0, den.sum(-1, keepdims=True), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(den > 0, num / np.where(den > 0, den, 1), tot)
    return r, den == 0


def factors(strategy: str, local: tuple, donor: tuple | None = None, k: float | None = None) -> dict:
    """Factors from sums. local/donor = (num, den), each (12,) or (B, 12). Returns arrays (B, 12)."""
    nl, dl = (np.atleast_2d(x) for x in local)
    kind = strategy.split(":")[0]
    if kind == "single":
        tot = nl.sum(-1, keepdims=True) / dl.sum(-1, keepdims=True)
        return {"a": np.repeat(tot, 12, axis=-1), "fallback": np.zeros(nl.shape, bool), "w_local": np.ones(nl.shape)}
    if kind == "local":
        a, fb = _ratio(nl, dl)
        return {"a": a, "fallback": fb, "w_local": np.ones(nl.shape)}
    if donor is None:
        raise ValueError(f"{strategy} needs donor sums")
    nd, dd = (np.atleast_2d(x) for x in donor)
    if kind == "donor":
        a, fb = _ratio(nd, dd)
        return {"a": a, "fallback": fb, "w_local": np.zeros(a.shape)}
    if kind == "pooled":
        a, fb = _ratio(nl + nd, dl + dd)
        with np.errstate(invalid="ignore"):
            return {"a": a, "fallback": fb, "w_local": dl / (dl + dd)}
    if kind == "blend":
        if k is None:
            raise ValueError("blend needs k")
        ad, fb = _ratio(nd, dd)
        with np.errstate(invalid="ignore", divide="ignore"):
            a = np.where(dl + k > 0, (nl + k * ad) / np.where(dl + k > 0, dl + k, 1), ad)
            w = np.where(dl + k > 0, dl / np.where(dl + k > 0, dl + k, 1), 0.0)
        return {"a": a, "fallback": fb, "w_local": w}
    raise ValueError(f"unknown strategy {strategy!r}")


def predict(a: np.ndarray, den: np.ndarray) -> np.ndarray:
    """Predicted numerator per (year, month): a (12,) times den (ny, 12)."""
    return np.asarray(a).reshape(1, 12) * den


def wape_bias(obs: np.ndarray, pred: np.ndarray) -> tuple[float, float]:
    tot = obs.sum()
    return float(np.abs(obs - pred).sum() / tot), float((pred - obs).sum() / tot)


def choose_k(local: YearMonth, donor: YearMonth, grid) -> tuple[float, pd.DataFrame]:
    """Leave-one-year-out WAPE of monthly totals for each k; returns the best k and the table."""
    rows = []
    for k in map(float, grid):
        obs, pred = [], []
        for y in local.years:
            fit_l, fit_d = local.select(set(local.years) - {y}), donor.select(set(donor.years) - {y})
            a = factors("blend", fit_l.sums(), fit_d.sums(), k)["a"][0]
            test = local.select([y])
            obs.append(test.num)
            pred.append(predict(a, test.den))
        wape, bias = wape_bias(np.concatenate(obs), np.concatenate(pred))
        rows.append({"k": float(k), "wape_loyo": wape, "bias_loyo": bias})
    t = pd.DataFrame(rows)
    return float(t.k[t.wape_loyo.idxmin()]), t


def bootstrap_weights(n_years: int, n: int, seed: int) -> np.ndarray:
    """(n, n_years) counts of each year in a resample with replacement."""
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_years, (n, n_years))
    return np.stack([np.bincount(d, minlength=n_years) for d in draws]).astype(float)


def fit_with_bootstrap(strategy: str, local: YearMonth, donor: YearMonth | None, k: float | None,
                       boot: dict) -> tuple[pd.DataFrame, np.ndarray]:
    """Point factors with percentile band, and the (B, 12) bootstrap draws.

    The same resampled years are used for local and donor (donor years must equal local years)."""
    point = factors(strategy, local.sums(), donor.sums() if donor else None, k)
    W = bootstrap_weights(len(local.years), boot["n"], boot["seed"])
    if donor is not None and not np.array_equal(donor.years, local.years):
        raise ValueError("donor and local years differ")
    draws = factors(strategy, local.sums(W), donor.sums(W) if donor else None, k)["a"]
    lo, hi = (1 - boot["ci"]) / 2, 1 - (1 - boot["ci"]) / 2
    nl, dl = local.sums()
    table = pd.DataFrame({
        "month": np.arange(1, 13), "a": point["a"][0],
        "a_low": np.nanquantile(draws, lo, axis=0), "a_high": np.nanquantile(draws, hi, axis=0),
        "w_local": point["w_local"][0], "fallback": point["fallback"][0],
        "n_local_num": nl, "n_local_den": dl,
    })
    return table, draws


# ---------- affine transfer (experiment, Phase 4): V = a_m * M + b_m ----------

def affine_fit(num: np.ndarray, den: np.ndarray, weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Per-month least squares V = a M + b across years, with a >= 0 and b >= 0.

    num/den are (ny, 12); weights (B, ny) are bootstrap year counts. Returns a, b of shape (B, 12).
    a < 0 is set to 0 (b = mean V); b < 0 falls back to the ratio of sums with b = 0.
    """
    W = np.ones((1, num.shape[0])) if weights is None else weights
    sw = W.sum(1, keepdims=True)
    mx, my = (W @ den) / sw, (W @ num) / sw
    sxx = (W @ den ** 2) / sw - mx ** 2
    sxy = (W @ (den * num)) / sw - mx * my
    with np.errstate(invalid="ignore", divide="ignore"):
        a = np.clip(np.where(sxx > 1e-12, sxy / np.where(sxx > 1e-12, sxx, 1), 0.0), 0, None)
        b = my - a * mx
        neg = b < 0
        ratio = np.where(mx > 0, my / np.where(mx > 0, mx, 1), 0.0)
    return np.where(neg, ratio, a), np.where(neg, 0.0, b)


def affine_factors(strategy: str, local: YearMonth, donor: YearMonth | None = None, k: float | None = None,
                   scale: float = 1.0, weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """affine_local | affine_blend:G (a and b blended) | affine_blend_a:G (a blended, b refitted locally).

    The donor intercept is multiplied by `scale` (local / donor footprint cells) because b is a count
    per region-month. Blend weight on local is w = M_L / (M_L + k), as for the ratio blend."""
    kind = strategy.split(":")[0]
    aL, bL = affine_fit(local.num, local.den, weights)
    if kind == "affine_local":
        return aL, bL
    aD, bD = affine_fit(donor.num, donor.den, weights)
    W = np.ones((1, local.num.shape[0])) if weights is None else weights
    ML = W @ local.den
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(ML + k > 0, ML / np.where(ML + k > 0, ML + k, 1), 0.0)
    a = w * aL + (1 - w) * aD
    if kind == "affine_blend":
        return a, w * bL + (1 - w) * bD * scale
    if kind == "affine_blend_a":
        sw = W.sum(1, keepdims=True)
        return a, np.clip((W @ local.num) / sw - a * (W @ local.den) / sw, 0, None)
    raise ValueError(f"unknown affine strategy {strategy!r}")
