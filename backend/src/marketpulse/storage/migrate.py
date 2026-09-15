"""Alembic migration'larını programatik çalıştırma ve şema hazır mı kontrolü."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

BACKEND_DIR = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
SCHEMA_SENTINEL_TABLE = "engine_heartbeat"


def run_migrations(sync_db_url: str) -> None:
    """`alembic upgrade head`. Senkron; async bağlamdan `asyncio.to_thread` ile çağrılır."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sync_db_url)
    command.upgrade(cfg, "head")


async def schema_ready(engine: AsyncEngine) -> bool:
    """Şema kurulmuş mu? Nöbetçi tablo `engine_heartbeat` üzerinden bakar."""
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    return SCHEMA_SENTINEL_TABLE in names


async def wait_for_schema(engine: AsyncEngine, *, timeout_sec: float, poll: float = 1.0) -> bool:
    """Şema hazır olana kadar bekler; süre dolunca False döner (çağıran migration'ı kendi koşar)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    while True:
        if await schema_ready(engine):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(poll)
