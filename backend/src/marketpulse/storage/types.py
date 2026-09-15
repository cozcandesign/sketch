"""SQLAlchemy sütun tipleri."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from marketpulse.core.time import ensure_utc


class UTCDateTime(TypeDecorator[datetime]):
    """Her zaman timezone-aware UTC.

    Bağlarken naive datetime reddedilir (CLAUDE.md §6). SQLite tz saklamaz; okurken UTC eklenir.
    Postgres/Timescale'de `timestamptz` olarak çalışır.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if not isinstance(value, datetime):
            msg = f"beklenmeyen datetime sonucu: {value!r}"
            raise TypeError(msg)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
