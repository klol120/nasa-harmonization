import pytest

from firecal.config import ConfigError, config_hash, load_config, region


def test_real_config_loads(cfg):
    assert set(cfg["regions"]) == {"lebanon", "greece", "eastmed"}
    assert cfg["grid"]["size_deg"] == 0.05
    assert cfg["sensors"]["satellites"] == ["Terra", "Aqua", "SNPP"]
    assert cfg["calibration"]["overlap_years"] == [2012, 2020]
    assert set(cfg["donors"]["israel_palestine"]["countries"]) == {"Israel", "Palestine"}


def test_bad_bbox_rejected():
    with pytest.raises(ConfigError, match="bbox"):
        load_config(overrides={"regions": {"x": {"bbox": [36, 33, 35, 34], "countries": ["Lebanon"]}}})


def test_bad_persistent_mode_rejected():
    with pytest.raises(ConfigError, match="mode"):
        load_config(overrides={"persistence": {"mode": "sometimes"}})


def test_unknown_region(cfg):
    with pytest.raises(ConfigError, match="unknown region"):
        region(cfg, "atlantis")


def test_hash_changes_with_config(cfg):
    other = load_config(overrides={"grid": {"size_deg": 0.1}})
    assert config_hash(cfg) != config_hash(other)
