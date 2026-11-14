import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    export_dir: Path
    cors_origins: list[str]


def settings() -> Settings:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set. Copy backend/.env.example to backend/.env and fill it in.")
    export_dir = Path(os.environ.get("EXPORT_DIR", "../export/export"))
    if not export_dir.is_absolute():
        export_dir = (BACKEND_DIR / export_dir).resolve()
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    return Settings(database_url=url, export_dir=export_dir, cors_origins=origins)
