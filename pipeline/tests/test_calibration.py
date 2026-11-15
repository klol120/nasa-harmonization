import numpy as np
import pytest

from firecal.calibration import (YearMonth, bootstrap_weights, choose_k, factors, fit_with_bootstrap, predict,
                                 wape_bias)

BOOT = {"n": 400, "seed": 7, "ci": 0.90}


def ym(num, den, years=None):
    num, den = np.atleast_2d(num).astype(float), np.atleast_2d(den).astype(float)
    return YearMonth(np.asarray(years or range(len(num))), num, den)


def test_wape_bias_hand_example():
    obs = np.array([[10.0, 20.0, 0.0]])
    pred = np.array([[12.0, 15.0, 1.0]])
    wape, bias = wape_bias(obs, pred)
    assert wape == pytest.approx((2 + 5 + 1) / 30)
    assert bias == pytest.approx((2 - 5 + 1) / 30)


def test_ratio_of_sums_not_mean_of_ratios():
    # month 1: years with 1/1 and 9/3 -> ratio of sums 10/4, not mean(1, 3) = 2
    num = np.zeros((2, 12)); den = np.ones((2, 12))
    num[:, 0], den[:, 0] = [1, 9], [1, 3]
    a = factors("local", ym(num, den).sums())["a"][0]
    assert a[0] == pytest.approx(10 / 4)


def test_zero_denominator_falls_back_to_all_month_ratio():
    num, den = np.full(12, 6.0), np.full(12, 2.0)
    num[3], den[3] = 5.0, 0.0
    f = factors("local", (num, den))
    assert f["fallback"][0, 3] and f["a"][0, 3] == pytest.approx(num.sum() / den.sum())


def test_single_is_one_ratio():
    num, den = np.arange(1, 13) * 3.0, np.arange(1, 13) * 1.0
    a = factors("single", (num, den))["a"][0]
    assert np.allclose(a, 3.0)


def test_blend_limits():
    local = (np.full(12, 40.0), np.full(12, 10.0))     # local ratio 4
    donor = (np.full(12, 200.0), np.full(12, 100.0))   # donor ratio 2
    assert np.allclose(factors("blend:d", local, donor, k=0)["a"], 4.0)
    assert np.allclose(factors("blend:d", local, donor, k=1e9)["a"], 2.0, atol=1e-6)
    f = factors("blend:d", local, donor, k=10)
    assert np.allclose(f["a"], (40 + 10 * 2) / (10 + 10)) and np.allclose(f["w_local"], 0.5)
    # no local MODIS at all: blend = donor, even with k = 0
    f0 = factors("blend:d", (np.zeros(12), np.zeros(12)), donor, k=0)
    assert np.allclose(f0["a"], 2.0) and np.allclose(f0["w_local"], 0.0)


def test_pooled_and_donor():
    local, donor = (np.full(12, 40.0), np.full(12, 10.0)), (np.full(12, 200.0), np.full(12, 100.0))
    assert np.allclose(factors("donor:d", local, donor)["a"], 2.0)
    assert np.allclose(factors("pooled:d", local, donor)["a"], 240 / 110)


def test_bootstrap_weights_are_resamples():
    W = bootstrap_weights(9, 100, 0)
    assert W.shape == (100, 9) and (W.sum(1) == 9).all() and (W >= 0).all()


def test_predict_shape():
    assert predict(np.arange(12), np.ones((3, 12))).shape == (3, 12)


def simulate_counts(rng, a_true, n_years=9, lam_m=None):
    """Binomial fire-day counts: MODIS ~ Poisson(lam), VIIRS ~ Poisson(a lam) per year-month."""
    lam = np.asarray(lam_m if lam_m is not None else np.linspace(30, 300, 12))
    lam_y = lam * rng.lognormal(0, 0.3, (n_years, 1))      # interannual variability
    den = rng.poisson(lam_y)
    num = rng.poisson(a_true * lam_y)
    return ym(num, den, list(range(2012, 2012 + n_years)))


def test_recovers_true_monthly_ratio():
    rng = np.random.default_rng(0)
    a_true = np.linspace(2.0, 5.0, 12)
    t = simulate_counts(rng, a_true, n_years=200)
    a = factors("local", t.sums())["a"][0]
    assert np.allclose(a, a_true, rtol=0.05)


def test_bootstrap_band_coverage():
    """The 90% year-bootstrap band should cover the true a_m about 90% of the time."""
    rng = np.random.default_rng(1)
    a_true = np.linspace(2.0, 5.0, 12)
    hits = []
    for seed in range(40):
        t = simulate_counts(rng, a_true)
        tab, _ = fit_with_bootstrap("local", t, None, None, {**BOOT, "seed": seed})
        hits.append((tab.a_low <= a_true) & (a_true <= tab.a_high))
    cover = np.mean(hits)
    assert 0.75 <= cover <= 0.98, cover


def test_choose_k_prefers_local_when_donor_is_wrong_and_local_is_rich():
    rng = np.random.default_rng(2)
    local = simulate_counts(rng, np.full(12, 4.0), lam_m=np.full(12, 500))
    donor = simulate_counts(rng, np.full(12, 2.0), lam_m=np.full(12, 500))
    k, table = choose_k(local, donor, [0, 10, 100, 1e9])
    assert k == 0 and table.wape_loyo.iloc[-1] > table.wape_loyo.iloc[0]


def test_choose_k_borrows_when_local_is_thin_and_donor_is_right():
    rng = np.random.default_rng(3)
    local = simulate_counts(rng, np.full(12, 3.0), lam_m=np.full(12, 1.5))
    donor = simulate_counts(rng, np.full(12, 3.0), lam_m=np.full(12, 800))
    k, _ = choose_k(local, donor, [0, 5, 20, 100, 1e9])
    assert k > 0


def test_fit_with_bootstrap_requires_same_years():
    rng = np.random.default_rng(4)
    a = simulate_counts(rng, np.full(12, 3.0))
    b = simulate_counts(rng, np.full(12, 3.0), n_years=5)
    with pytest.raises(ValueError, match="years"):
        fit_with_bootstrap("pooled:x", a, b, None, BOOT)


def test_affine_fit_recovers_line_and_constraints():
    from firecal.calibration import affine_fit
    rng = np.random.default_rng(5)
    den = rng.uniform(0, 50, (30, 12))
    num = 3.0 * den + 20.0 + rng.normal(0, 0.5, den.shape)
    a, b = affine_fit(num, den)
    assert np.allclose(a, 3.0, atol=0.05) and np.allclose(b, 20.0, atol=1.0)
    # MODIS constant zero: slope 0, intercept = mean VIIRS
    a0, b0 = affine_fit(np.full((5, 12), 7.0), np.zeros((5, 12)))
    assert np.allclose(a0, 0) and np.allclose(b0, 7.0)
    # a negative intercept falls back to the ratio of sums
    a1, b1 = affine_fit(np.array([[1.0] * 12, [9.0] * 12]), np.array([[1.0] * 12, [3.0] * 12]))
    assert np.allclose(b1, 0) and np.allclose(a1, 10 / 4)


def test_affine_blend_limits():
    from firecal.calibration import affine_factors
    rng = np.random.default_rng(6)
    d1 = rng.uniform(5, 50, (8, 12)); d2 = rng.uniform(50, 500, (8, 12))
    local, donor = ym(2 * d1 + 10, d1), ym(4 * d2 + 100, d2)
    a, b = affine_factors("affine_blend:x", local, donor, k=0, scale=0.1)
    assert np.allclose(a, 2) and np.allclose(b, 10)
    a, b = affine_factors("affine_blend:x", local, donor, k=1e12, scale=0.1)
    assert np.allclose(a, 4, atol=1e-6) and np.allclose(b, 10, atol=1e-4)    # donor b scaled: 100 * 0.1


def test_shape_level_keeps_annual_total_and_shape():
    from firecal.calibration import shape_level
    shape = np.array([[1.0, 3.0, 0.0, 6.0], [0.0, 0.0, 0.0, 0.0]])
    level = np.array([[5.0, 5.0, 5.0, 5.0], [1.0, 2.0, 3.0, 4.0]])
    out = shape_level(shape, level)
    assert np.allclose(out.sum(1), level.sum(1))
    assert np.allclose(out[0], np.array([1, 3, 0, 6]) * 2.0)      # shape kept, scaled 20/10
    assert np.allclose(out[1], level[1])                         # zero shape -> level
    flat = shape_level(shape.ravel(), level.ravel(), np.repeat([2001, 2002], 4))
    assert np.allclose(flat, out.ravel())
