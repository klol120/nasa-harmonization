"""Outlook model: inputs never look past the issue month; scores and bands behave."""

import math

import pytest

np = pytest.importorskip("numpy")  # the `ml` dependency group

from firecal_api import outlook as O  # noqa: E402


def synthetic(n_cells=20, years=12, seed=1) -> O.Region:
    rng = np.random.default_rng(seed)
    months = [f"{2010 + k // 12:04d}-{k % 12 + 1:02d}" for k in range(12 * years)]
    season = np.array([0, 0, 0, 1, 2, 4, 8, 9, 6, 3, 1, 0], dtype=np.float32)
    lam = np.tile(season, years)[None, :] * rng.uniform(0.2, 2, (n_cells, 1))
    V = rng.poisson(lam).astype(np.float32)
    return O.Region(
        name="test", months=months, cells=[f"{1000 + c}_2000" for c in range(n_cells)], V=V,
        ok=np.ones(len(months), bool),
        lat=np.linspace(33, 34, n_cells, dtype=np.float32), lon=np.linspace(35, 36, n_cells, dtype=np.float32),
        mean=V.mean(axis=0),
    )


@pytest.mark.parametrize("h", list(O.HORIZONS))
def test_features_use_only_months_up_to_issue(h):
    R = synthetic()
    i = 100
    before = O.features(R, 0, i, h)
    R.V[:, i + 1:] = 999.0  # change every month after the issue month
    R.mean[i + 1:] = 999.0
    after = O.features(R, 0, i, h)
    assert before.shape == (len(R.cells), len(O.FEATURES))
    assert np.allclose(before, after, equal_nan=True)


def test_target_month_and_lead_are_inputs():
    R = synthetic()
    X = O.features(R, 0, 100, 3)  # issued after 2018-05 -> target 2018-08
    assert R.months[100] == "2018-05"
    assert (X[:, O.FEATURES.index("month")] == 8).all()
    assert (X[:, O.FEATURES.index("h")] == 3).all()
    # last year's value is the same calendar month one year earlier
    assert np.allclose(X[:, O.FEATURES.index("ly")], R.V[:, R.months.index("2017-08")])


def test_backtest_drops_issues_before_the_shared_fit_cutoff():
    class Constant:
        def predict(self, inputs):
            return np.ones(len(inputs))

    region = synthetic()
    jan = region.idx("2020-01")
    july = region.idx("2020-07")
    scored = O.score(Constant(), [region], {region.name: [jan, july]}, fitted_through="2019-12")[region.name]
    assert [r["h"] for r in scored if r["ym"] == "2020-01"] == [1]
    assert [r["h"] for r in scored if r["ym"] == "2020-07"] == list(O.HORIZONS)
    assert all(r["issue"] >= "2019-12" for r in scored)


def test_uses_the_strongest_baseline_when_the_blend_does_not_improve():
    row = {"h": 1, "ym": "2023-01", "actual": 10, "model": 12, "seasonal_5y": 12,
           "typical_year": 11, "last_year": 15}
    assert O.pick_method([row]) == "typical_year"
    assert O.evaluate([row], "typical_year", (0.0, 0.0))["model"]["wape"] == pytest.approx(0.1)
    assert O.pick_method([{**row, "model": 10}]) == "outlook"
    assert O.pick_method([{**row, "model": 11}]) == "typical_year"


def test_summarize_and_band():
    rows = [{"h": 1, "ym": "2020-01", "actual": 10.0, "model": 12.0, "seasonal_5y": 20.0, "typical_year": 15.0,
             "last_year": 5.0},
            {"h": 1, "ym": "2020-02", "actual": 30.0, "model": 27.0, "seasonal_5y": 20.0, "typical_year": 25.0,
             "last_year": 40.0}]
    s = O.summarize(rows)
    assert s["model"]["mae"] == pytest.approx(2.5)
    assert s["best_baseline"] == "typical_year" and s["beats_baselines"]
    assert s["skill_vs_typical_year"] == pytest.approx(1 - 2.5 / 5.0)
    lo, hi = O._band(10.0, (math.log(0.5), math.log(2)))
    assert lo == pytest.approx(4.5) and hi == pytest.approx(21.0)


def test_fit_and_predict_on_synthetic_data():
    pytest.importorskip("sklearn")
    R = synthetic(n_cells=40)
    last = {R.name: R.months.index("2019-12")}
    m, n = O.fit([R], last)
    assert n > 0
    p = m.predict(O.features(R, 0, R.months.index("2020-06"), 1))  # forecast July
    assert p.shape == (40,) and (p >= 0).all()
    # July is the peak month of the synthetic season: the forecast should be well above a winter month
    q = m.predict(O.features(R, 0, R.months.index("2020-12"), 1))  # forecast January
    assert p.sum() > 3 * q.sum()
    assert m.with_blend(1.0).predict(O.features(R, 0, 120, 1)) == pytest.approx(
        np.nan_to_num(O.features(R, 0, 120, 1)[:, O.FEATURES.index("m5")]))


def test_blend_weights_and_range_coverage():
    rows = [{"h": 1, "ym": "2020-01", "actual": 10.0, "raw": 20.0, "seasonal_5y": 10.0, "typical_year": 9.0, "last_year": 8.0},
            {"h": 1, "ym": "2020-02", "actual": 30.0, "raw": 40.0, "seasonal_5y": float("nan"), "typical_year": 25.0,
             "last_year": 40.0}]
    half = O.blended(rows, 0.5)
    assert half[0]["model"] == pytest.approx(15.0)
    assert half[1]["model"] == pytest.approx(40.0)  # no 5-year mean yet: the model alone
    assert O.blended(rows, 1.0)[0]["model"] == pytest.approx(10.0)  # weight 1 = the 5-year mean
    q = O.band_quantiles(O.blended(rows, 1.0))
    assert q[0] <= 0 <= q[1] or q[0] <= q[1]
    assert O.coverage(O.blended(rows, 1.0), (math.log(0.5), math.log(2))) == pytest.approx(1.0)
    assert O.coverage([], (0.0, 0.0)) is None
    assert "5-year average" in O.method_text(1.0) and O.method_text(0.0) == "machine-learning model"
