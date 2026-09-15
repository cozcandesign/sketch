"""SQLite repository taban sınıfı: engine tutma, şema oluşturma, JSON yardımcıları."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from marketpulse.storage import tables as t


def json_default(value: object) -> str:
    """datetime'ları ISO-8601 yazar; diğerlerini str()."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def dump_json(value: Any) -> str:
    return json.dumps(value, default=json_default)


def load_json(raw: str | None) -> Any:
    return None if raw is None else json.loads(raw)


class SqliteBase:
    """Ortak engine ve şema işlemleri. Mixin'ler bu sınıftan türer."""

    def __init__(self, engine: AsyncEngine, *, db_url: str | None = None) -> None:
        self._engine = engine
        self._db_url = db_url

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(t.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()
