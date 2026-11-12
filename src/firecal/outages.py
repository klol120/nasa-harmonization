"""Satellite outage days: confirmed list from config plus statistical suspects.

A satellite-day is a suspect when it has zero detections over the reference regions although the
centred rolling median of that satellite's daily counts (lambda) makes zero unlikely:
P(0 | Poisson(lambda)) = exp(-lambda) < p_threshold. Suspects are listed for review and only flagged
when gaps.use_suspects is true. Outage days are never filled.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .config import as_date

COLUMNS = ["satellite", "date", "kind", "flagged", "note", "expected"]


def satellite_coverage(cfg: dict) -> dict[str, tuple[dt.date, dt.date]]:
    """Date span each configured satellite has data, from config coverage."""
    cov = {k: (as_date(a), as_date(b)) for k, (a, b) in cfg["coverage"].items()}
    out = {}
    for sat in cfg["sensors"]["satellites"]:
        if sat in ("Terra", "Aqua"):
            a, b = cov["MODIS_SP"]
            if sat == "Aqua":
                a = max(a, as_date(cfg["sensors"]["terra_only_until"]))
        else:
            a, b = cov[f"VIIRS_{sat}_SP"]
        out[sat] = (a, b)
    return out


def known(cfg: dict) -> pd.DataFrame:
    rows = []
    for k in cfg["gaps"].get("known", []):
        for d in pd.date_range(as_date(k["start"]), as_date(k["end"])):
            rows.append((k["satellite"], d.date(), "known", True, k.get("note", ""), np.nan))
    return pd.DataFrame(rows, columns=COLUMNS)


def suspects(cfg: dict, detections: pd.DataFrame) -> pd.DataFrame:
    g = cfg["gaps"]
    lam_min = -np.log(g["p_threshold"])
    day = detections.datetime_utc.dt.tz_convert(None).dt.normalize()
    counts = detections.assign(day=day).groupby(["satellite", "day"], observed=True).size()
    rows = []
    for sat, (a, b) in satellite_coverage(cfg).items():
        days = pd.date_range(a, b)
        has = sat in counts.index.get_level_values(0)
        c = (counts[sat] if has else pd.Series(dtype=float)).reindex(days, fill_value=0)
        lam = c.rolling(g["window_days"], center=True, min_periods=g["window_days"] // 2).median()
        hit = (c == 0) & (lam > lam_min)
        for d in c.index[hit]:
            rows.append((sat, d.date(), "suspect", bool(g.get("use_suspects", False)), "", float(lam[d])))
    return pd.DataFrame(rows, columns=COLUMNS)


def build(cfg: dict, reference_detections: pd.DataFrame) -> pd.DataFrame:
    k = known(cfg)
    s = suspects(cfg, reference_detections)
    s = s[~s.set_index(["satellite", "date"]).index.isin(k.set_index(["satellite", "date"]).index)]
    out = pd.concat([k, s], ignore_index=True).sort_values(["satellite", "date"], ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out["expected"] = out["expected"].astype(float)
    return out


def runs(outages: pd.DataFrame) -> pd.DataFrame:
    """Collapse consecutive days into (satellite, kind, start, end, days) runs for reports."""
    if outages.empty:
        return pd.DataFrame({"satellite": pd.Series(dtype=str), "kind": pd.Series(dtype=str),
                             "start": pd.Series(dtype="datetime64[ns]"), "end": pd.Series(dtype="datetime64[ns]"),
                             "days": pd.Series(dtype=int)})
    o = outages.sort_values(["satellite", "kind", "date"])
    brk = (o.date.diff() != pd.Timedelta(days=1)) | (o.satellite != o.satellite.shift()) | (o.kind != o.kind.shift())
    o = o.assign(run=brk.cumsum())
    return o.groupby("run").agg(satellite=("satellite", "first"), kind=("kind", "first"), start=("date", "min"),
                                end=("date", "max"), days=("date", "size")).reset_index(drop=True)


def write_suspects_report(cfg: dict, outages: pd.DataFrame, out_path) -> None:
    """docs/reports/outage_suspects.md: suspect runs for checking against NASA outage notices.

    Order: gaps.review_first, then runs inside a calibration window (a_m overlap years for every
    satellite, terra.fit_years for Terra/Aqua) by strength of evidence, then the rest by date."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    s = outages[outages.kind == "suspect"].copy()
    if s.empty:
        out_path.write_text("# Outage suspects\n\nNone.\n")
        return
    s["p0"] = np.exp(-s.expected)
    r = runs(s)
    lam = []
    for row in r.itertuples():
        m = (s.satellite == row.satellite) & s.date.between(row.start, row.end)
        lam.append((s.expected[m].min(), s.p0[m].max()))
    r["min_expected"], r["max_p0"] = zip(*lam)
    o0, o1 = cfg["calibration"]["overlap_years"]
    t0, t1 = cfg["terra"]["fit_years"]
    y = r.start.dt.year
    in_overlap = y.between(o0, o1)
    in_terra = r.satellite.isin(["Terra", "Aqua"]) & y.between(t0, t1)
    r["window"] = np.select([in_overlap, in_terra], [f"a_m fit {o0}-{o1}", f"kT fit {t0}-{t1}"], "")
    pinned = np.zeros(len(r), bool)
    why = pd.Series("", index=r.index)
    for p in cfg["gaps"].get("review_first", []):
        hit = (r.satellite == p["satellite"]) & (r.start <= pd.Timestamp(as_date(p["end"]))) & \
              (r.end >= pd.Timestamp(as_date(p["start"])))
        pinned |= hit.to_numpy()
        why[hit] = p.get("why", "")
    r["pinned"], r["pin_why"] = pinned, why
    r["group"] = np.where(r.pinned, 0, np.where(r.window != "", 1, 2))
    r = r.sort_values(["group", "max_p0", "start"], ascending=[True, True, True])
    lines = [
        "# Outage suspects (for review; not flagged, gaps.use_suspects = false)", "",
        "A suspect is a satellite-day with **zero detections** over the reference regions "
        f"({', '.join(cfg['gaps']['reference_regions'])}) while the centred {cfg['gaps']['window_days']}-day median "
        "of that satellite's daily detection count (lambda) makes zero unlikely: "
        f"P(0 | Poisson(lambda)) = exp(-lambda) < {cfg['gaps']['p_threshold']}. "
        "Consecutive days are merged into runs. Check each run against NASA's published outage notices; "
        "confirmed ones go into `gaps.known` in config.yaml.", "",
        "| # | satellite | start | end | days | expected detections/day (min) | P(0) (max) | calibration window | note |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, x in enumerate(r.itertuples(), 1):
        note = ("**review first**: " + x.pin_why) if x.pinned else ""
        lines.append(f"| {i} | {x.satellite} | {x.start:%Y-%m-%d} | {x.end:%Y-%m-%d} | {x.days} | "
                     f"{x.min_expected:.0f} | {x.max_p0:.1e} | {x.window} | {note} |")
    k = runs(outages[outages.kind == "known"])
    lines += ["", "Confirmed outages already in config (`gaps.known`):", ""]
    lines += [f"- {x.satellite} {x.start:%Y-%m-%d} to {x.end:%Y-%m-%d} ({x.days} days)" for x in k.itertuples()]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
