"""Async engine fabrikası. SQLite için WAL ve diğer PRAGMA'lar bağlantı açılışında uygulanır."""

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# busy_timeout ilk sırada: sonraki PRAGMA'lar (özellikle journal_mode) anlık kilitte
# hata vermek yerine bekler.
SQLITE_PRAGMAS: tuple[str, ...] = (
    "PRAGMA busy_timeout=5000",
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
)

_SQLITE_PREFIX = "sqlite+aiosqlite:///"


def sqlite_file_path(db_url: str) -> Path | None:
    """`sqlite+aiosqlite:///path` biçiminden dosya yolunu çıkarır; bellek DB'si için None."""
    if not db_url.startswith(_SQLITE_PREFIX):
        return None
    path = db_url[len(_SQLITE_PREFIX) :]
    if path in {"", ":memory:"} or path.startswith("file::memory"):
        return None
    return Path(path)


def make_engine(db_url: str, *, echo: bool = False) -> AsyncEngine:
    """Engine oluşturur; SQLite dosyası için üst dizini yaratır ve PRAGMA'ları bağlar."""
    file_path = sqlite_file_path(db_url)
    if file_path is not None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(db_url, echo=echo, future=True)
    if db_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            for pragma in SQLITE_PRAGMAS:
                cursor.execute(pragma)
            cursor.close()

    return engine
