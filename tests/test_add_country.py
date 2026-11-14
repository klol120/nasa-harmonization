"""add-country pure parts: region id, bbox, donor pool excluding the country, grade."""
from firecal.add_country import country_bbox, grade, region_overlay, slug
from firecal.config import load_config


def test_slug():
    assert slug("Bosnia and Herzegovina") == "bosnia_and_herzegovina"


def test_bbox_drops_remote_islands_keeps_thrace():
    cfg = load_config()
    w, s, e, n = country_bbox(cfg, "Portugal")
    assert w > -10 and s > 36                    # Azores (-31 W) and Madeira (32.6 N) excluded
    w, *_ = country_bbox(cfg, "Turkey")
    assert w < 26.5                              # European part (Thrace) kept


def test_pool_excludes_the_country():
    cfg = load_config()
    body = region_overlay(cfg, "Syria", "syria")
    (g, d), = body["donors"].items()
    assert "Syria" not in d["countries"] and d["for_regions"] == ["syria"]
    assert body["auto_strategy"]["by_region"]["syria"]["outcomes"]["donor_only"] == f"donor:{g}"
    assert "donors" not in region_overlay(cfg, "Jordan", "jordan")


def test_grade():
    cfg = load_config()
    s = {"auto": {"outcome": "rich"}, "continuity_2012": {"flagged": False, "step_index": 1.0},
         "holdout": {"forward": {"wape": 0.2, "bias": 0.05}, "reverse": {"wape": 0.3, "bias": -0.15}}}
    assert grade(cfg, s)[0] == "B"
    assert grade(cfg, {**s, "continuity_2012": {"flagged": True, "step_index": 1.3}})[0] == "D"
    assert grade(cfg, {**s, "auto": {"outcome": "donor_only"}})[0] == "D"
