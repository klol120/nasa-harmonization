from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from firecal.config import load_config
from synthetic import SynthSpec, config_overrides, write_csvs

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture
def synth(tmp_path):
    """Small synthetic region (2010-2014) written as Phase 0 region files; returns (cfg, spec, written)."""
    spec = SynthSpec(seed=1, start=dt.date(2010, 1, 1), end=dt.date(2014, 12, 31))
    written = write_csvs(spec, tmp_path / "raw")
    return load_config(overrides=config_overrides(spec, tmp_path)), spec, written
