import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND / ".env")

EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", "../pipeline/data/export"))
if not EXPORT_DIR.is_absolute():
    EXPORT_DIR = (BACKEND / EXPORT_DIR).resolve()
LEBANON = EXPORT_DIR / "lebanon"

# Database tests run against a separate "<name>_test" database, never the real one.
_url = os.environ.get("DATABASE_URL")
TEST_DB_URL = None
if _url:
    parts = urlsplit(_url)
    TEST_DB_URL = urlunsplit(parts._replace(path=parts.path.rstrip("/") + "_test"))
    os.environ["DATABASE_URL"] = TEST_DB_URL  # before firecal_api.config is imported


def pytest_collection_modifyitems(config, items):
    skip_db = pytest.mark.skip(reason="DATABASE_URL not set (backend/.env)")
    skip_data = pytest.mark.skip(reason=f"export data not found at {LEBANON}")
    for item in items:
        if "db" in item.keywords and not TEST_DB_URL:
            item.add_marker(skip_db)
        if not LEBANON.is_dir():
            item.add_marker(skip_data)


def pytest_configure(config):
    config.addinivalue_line("markers", "db: needs PostgreSQL (uses a separate <name>_test database)")
