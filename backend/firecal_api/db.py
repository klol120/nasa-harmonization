"""Connections and schema migrations."""

import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

SQL_DIR = Path(__file__).parent / "sql"


async def _init_conn(conn: asyncpg.Connection) -> None:
    # jsonb columns in and out as Python objects.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def connect(url: str) -> asyncpg.Connection:
    conn = await asyncpg.connect(url)
    await _init_conn(conn)
    return conn


async def create_pool(url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(url, min_size=1, max_size=8, init=_init_conn)


async def ensure_database(url: str) -> bool:
    """Create the database named in the URL if it does not exist. Returns True if created."""
    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    if not name or not name.replace("_", "").isalnum():
        raise SystemExit(f"Refusing to create database with name {name!r}")
    admin = urlunsplit(parts._replace(path="/postgres"))
    conn = await asyncpg.connect(admin)
    try:
        if await conn.fetchval("select 1 from pg_database where datname = $1", name):
            return False
        await conn.execute(f'create database "{name}"')
        return True
    finally:
        await conn.close()


async def migrate(conn: asyncpg.Connection) -> list[str]:
    """Apply sql/NNN_*.sql files not applied yet, in order. Returns the names applied."""
    await conn.execute(
        "create table if not exists schema_migration (name text primary key, applied_at timestamptz not null default now())"
    )
    done = {r["name"] for r in await conn.fetch("select name from schema_migration")}
    applied = []
    for f in sorted(SQL_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        if f.name in done:
            continue
        async with conn.transaction():
            await conn.execute(f.read_text(encoding="utf-8"))
            await conn.execute("insert into schema_migration (name) values ($1)", f.name)
        applied.append(f.name)
    return applied
