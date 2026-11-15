import copy

import numpy as np
import pandas as pd
import pytest

from firecast.regional_similarity import distances, profile


def fixture():
    days = pd.date_range("2019-01-01", "2020-12-31")
    w = pd.DataFrame({"date": days, "weather_point_id": "land", "lat": 34., "lon": 36.,
                      "T2M": 20., "T2M_MAX": 25., "RH2M": 50., "PRECTOTCORR": 1.})
    c = pd.DataFrame({"cell_id": ["one"], "lat": [34.], "lon": [36.],
                      "elevation_m": [400.], "slope_deg": [10.], "vegetation_fraction": [.8]})
    return w, c


def test_environment_profile_uses_past_only_and_actual_calendar_lengths():
    weather, cells = fixture()
    base = profile(weather, cells, "2019-01-01", "2021-01-01")
    assert base["summary"]["annual_rain_mm"] == 365.5
    future = weather.iloc[:1].assign(date=pd.Timestamp("2021-01-01"), T2M=9999.)
    changed = profile(pd.concat([weather, future], ignore_index=True), cells, "2019-01-01", "2021-01-01")
    assert changed == base


def test_unassigned_ocean_points_cannot_distort_land_weather():
    weather, cells = fixture()
    ocean = weather.assign(weather_point_id="ocean", lat=30., lon=30., T2M=1000., PRECTOTCORR=1000.)
    result = profile(pd.concat([weather, ocean], ignore_index=True), cells, "2019-01-01", "2021-01-01")
    assert result["summary"]["annual_temperature_c"] == 20.
    assert result["summary"]["used_weather_points"] == 1


def test_missing_duplicate_or_invalid_development_days_rejected():
    weather, cells = fixture()
    for bad in [weather.iloc[1:], pd.concat([weather, weather.iloc[:1]]), weather.assign(T2M=np.nan)]:
        with pytest.raises(ValueError):
            profile(bad, cells, "2019-01-01", "2021-01-01")


def test_distance_does_not_fit_scaling_on_target_or_accept_duplicate_sources():
    weather, cells = fixture()
    a = profile(weather, cells, "2019-01-01", "2021-01-01")
    b = profile(weather.assign(T2M=30.), cells, "2019-01-01", "2021-01-01")
    target = copy.deepcopy(a)
    profiles = {"a": a, "b": b, "target": target}
    d = distances(profiles, "target", ["a", "b"], [.25] * 4)
    assert d[0]["region"] == "a" and d[0]["standardized_distance"] == 0
    with pytest.raises(ValueError):
        distances(profiles, "target", ["a", "target"], [.25] * 4)
    with pytest.raises(ValueError):
        distances(profiles, "target", ["a", "a"], [.25] * 4)
