"""Automatic calibration-strategy choice from data thinness (for add-country).

The thresholds in config `auto_strategy` come from a cell-subsampling experiment
(docs/reports/thresholds.md); this module only applies them:

  annual = sum of n over the overlap years / number of years, where n = local MODIS fire-days in a
           calendar month on the fitting inputs (usable dates, persistent fire-days excluded when
           configured), exactly the denominator of a_m;
  annual < n_min_annual            -> outcomes.donor_only (the donor pool alone)
  share of months with n < n_month >= n_country -> outcomes.thin (Lebanon strategy)
  otherwise                        -> outcomes.rich (local monthly ratios)

`decide` also records, per calendar month, which rule fired and why, for meta.json.
"""
from __future__ import annotations

from .fitting import FitSpec, chosen, components, donor_groups, table

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _available(cfg: dict, region: str, strategy: str) -> bool:
    groups = donor_groups(cfg, region)
    return all(not s.partition(":")[2] or s.partition(":")[2] in groups for s in components(cfg, strategy))


def decide(cfg: dict, region: str) -> dict:
    a = cfg["auto_strategy"]
    y0, y1 = cfg["calibration"]["overlap_years"]
    years = list(range(y0, y1 + 1))
    excl = cfg["persistence"]["exclude_from_calibration"]
    n = table(cfg, region, FitSpec("a", years, excl)).den.sum(0)
    annual = float(n.sum() / len(years))
    thin = n < a["n_month"]
    share = float(thin.mean())
    out = a["outcomes"]
    if annual < a["n_min_annual"]:
        outcome = "donor_only"
        region_reason = f"annual local MODIS fire-days {annual:.1f} < n_min_annual {a['n_min_annual']}"
    elif share >= a["n_country"]:
        outcome = "thin"
        region_reason = (f"{int(thin.sum())}/12 months thin (n < n_month {a['n_month']}): share {share:.2f} "
                         f">= n_country {a['n_country']}")
    else:
        outcome = "rich"
        region_reason = (f"{int(thin.sum())}/12 months thin (n < n_month {a['n_month']}): share {share:.2f} "
                         f"< n_country {a['n_country']}")
    strategy = out[outcome]

    months = []
    for m in range(12):
        nm = int(n[m])
        test = f"n {nm} {'<' if thin[m] else '>='} n_month {a['n_month']}"
        if outcome == "donor_only":
            rule, why = "n_min", f"region below n_min_annual: donor pool ratio for every month ({test})"
        elif outcome == "thin" and thin[m]:
            rule, why = "thin_month", f"{test}: monthly shape borrowed from the donor pool, level from the local single ratio"
        elif outcome == "thin":
            rule, why = ("n_country", f"{test}, but the region is thin overall: the composite's shape still blends "
                                      "this month toward local in proportion to n (w = n / (n + k))")
        elif thin[m]:
            rule, why = "n_country", f"{test}, but too few thin months to borrow (region rule): local ratio kept"
        else:
            rule, why = "rich_month", f"{test}: local monthly ratio"
        months.append({"month": m + 1, "name": MONTHS[m], "n": nm, "thin": bool(thin[m]), "rule": rule, "reason": why})

    configured = chosen(cfg, "calibration", region)
    return {
        "strategy": strategy, "outcome": outcome, "reason": region_reason,
        "available": _available(cfg, region, strategy),
        "configured_strategy": configured, "agrees_with_configured": strategy == configured,
        "inputs": {"overlap_years": [y0, y1], "exclude_persistent": excl, "annual": round(annual, 2),
                   "thin_share": round(share, 4)},
        "thresholds": {k: a[k] for k in ("n_month", "n_country", "n_country_annual", "n_min_annual")},
        "report": a.get("report"),
        "months": months,
    }
