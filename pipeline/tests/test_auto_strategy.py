"""Data-thinness rule (config auto_strategy, docs/reports/thresholds.md)."""
import numpy as np
import pytest

from firecal import auto_strategy
from firecal.calibration import YearMonth
from firecal.config import load_config

# n per calendar month (local MODIS fire-days, 2012-2020, persistence excluded), docs/reports/thresholds.md
LEBANON = [3, 2, 3, 4, 5, 27, 56, 66, 116, 133, 53, 10]
GREECE = [179, 423, 461, 247, 118, 277, 732, 972, 1152, 2085, 948, 195]


@pytest.fixture
def cfg():
    return load_config()


def fake_table(n_by_month, years=9):
    den = np.tile(np.asarray(n_by_month, float) / years, (years, 1))
    return lambda *a, **k: YearMonth(np.arange(2012, 2012 + years), den * 2, den)


@pytest.mark.parametrize("n, region, outcome, strategy", [
    (LEBANON, "lebanon", "thin", "affine_shape_single_level_pool"),
    (GREECE, "greece", "rich", "local"),
    ([2] * 12, "lebanon", "donor_only", "donor:eastmed_pool"),     # 2.7 a year < n_min_annual
])
def test_outcomes(monkeypatch, cfg, n, region, outcome, strategy):
    monkeypatch.setattr(auto_strategy, "table", fake_table(n))
    d = auto_strategy.decide(cfg, region)
    assert (d["outcome"], d["strategy"]) == (outcome, strategy)
    assert len(d["months"]) == 12 and all(m["reason"] for m in d["months"])


def test_month_records(monkeypatch, cfg):
    monkeypatch.setattr(auto_strategy, "table", fake_table(GREECE))
    d = auto_strategy.decide(cfg, "greece")
    may = d["months"][4]
    assert may["thin"] and may["rule"] == "n_country"            # thin month, region rule keeps local
    assert d["months"][9]["rule"] == "rich_month"


def test_regression_v1_strategies(monkeypatch, cfg):
    """The derived thresholds pick the v1.0-data strategies for Greece and Lebanon."""
    for n, region in ((LEBANON, "lebanon"), (GREECE, "greece")):
        monkeypatch.setattr(auto_strategy, "table", fake_table(n))
        d = auto_strategy.decide(cfg, region)
        assert d["agrees_with_configured"], (region, d["strategy"], d["configured_strategy"])
