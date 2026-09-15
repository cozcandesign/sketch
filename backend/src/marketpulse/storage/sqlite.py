"""SQLite repository implementasyonu (SQLAlchemy Core + aiosqlite)."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from marketpulse.storage import tables as t
from marketpulse.storage.db import sqlite_file_path
from marketpulse.storage.models import CollectorHealth, Heartbeat, OutboxEvent

HEARTBEAT_ROW_ID = 1


def _json_default(value: object) -> str:
    """Outbox payload'ındaki datetime'lar ISO-8601 olarak serileşir; diğerleri str()."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class SqliteRepository:
    """`Repository` protokolünün SQLite gerçekleştirimi. Tek engine, kısa transaction'lar."""

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

    # --- engine heartbeat ---

    async def write_heartbeat(self, ts: datetime, version: str) -> None:
        stmt = sqlite_insert(t.engine_heartbeat).values(id=HEARTBEAT_ROW_ID, ts=ts, version=version)
        stmt = stmt.on_conflict_do_update(
            index_elements=[t.engine_heartbeat.c.id], set_={"ts": ts, "version": version}
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def read_heartbeat(self) -> Heartbeat | None:
        stmt = select(t.engine_heartbeat.c.ts, t.engine_heartbeat.c.version).where(
            t.engine_heartbeat.c.id == HEARTBEAT_ROW_ID
        )
        async with self._engine.connect() as conn:
            row = (await conn.execute(stmt)).first()
        if row is None:
            return None
        return Heartbeat(ts=row.ts, version=row.version)

    async def clear_heartbeat(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                delete(t.engine_heartbeat).where(t.engine_heartbeat.c.id == HEARTBEAT_ROW_ID)
            )

    # --- collector sağlığı ---

    async def upsert_collector_health(self, health: CollectorHealth) -> None:
        values = health.model_dump()
        stmt = sqlite_insert(t.collector_health).values(**values)
        update_cols = {k: v for k, v in values.items() if k != "collector"}
        stmt = stmt.on_conflict_do_update(
            index_elements=[t.collector_health.c.collector], set_=update_cols
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def list_collector_health(self) -> list[CollectorHealth]:
        stmt = select(t.collector_health).order_by(t.collector_health.c.collector)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [CollectorHealth(**dict(row)) for row in rows]

    # --- outbox ---

    async def outbox_emit(self, topic: str, payload: dict[str, Any], created_at: datetime) -> int:
        payload_json = json.dumps(payload, default=_json_default)
        stmt = t.events_outbox.insert().values(
            created_at=created_at, topic=topic, payload_json=payload_json
        )
        async with self._engine.begin() as conn:
            result = await conn.execute(stmt)
        pk = result.inserted_primary_key
        if pk is None:
            msg = "outbox insert birincil anahtar döndürmedi"
            raise RuntimeError(msg)
        return int(pk[0])

    async def outbox_read_after(self, last_id: int, limit: int = 500) -> list[OutboxEvent]:
        stmt = (
            select(t.events_outbox)
            .where(t.events_outbox.c.id > last_id)
            .order_by(t.events_outbox.c.id)
            .limit(limit)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [
            OutboxEvent(
                id=row["id"],
                created_at=row["created_at"],
                topic=row["topic"],
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    async def outbox_max_id(self) -> int:
        async with self._engine.connect() as conn:
            value = (await conn.execute(select(func.max(t.events_outbox.c.id)))).scalar()
        return int(value or 0)

    async def outbox_prune(self, before: datetime) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                delete(t.events_outbox).where(t.events_outbox.c.created_at < before)
            )
        return int(result.rowcount or 0)

    # --- ayarlar ---

    async def get_setting(self, key: str) -> Any | None:
        stmt = select(t.settings_table.c.value_json).where(t.settings_table.c.key == key)
        async with self._engine.connect() as conn:
            raw = (await conn.execute(stmt)).scalar()
        return None if raw is None else json.loads(raw)

    async def set_setting(self, key: str, value: Any, updated_at: datetime) -> None:
        value_json = json.dumps(value)
        stmt = sqlite_insert(t.settings_table).values(
            key=key, value_json=value_json, updated_at=updated_at
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[t.settings_table.c.key],
            set_={"value_json": value_json, "updated_at": updated_at},
        )
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    # --- meta ---

    async def db_size_bytes(self) -> int | None:
        if self._db_url is None:
            return None
        path = sqlite_file_path(self._db_url)
        if path is None or not path.exists():
            return None
        size = path.stat().st_size
        wal = path.with_name(path.name + "-wal")
        if wal.exists():
            size += wal.stat().st_size
        return size
