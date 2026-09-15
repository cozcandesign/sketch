from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import StatementError

from marketpulse.storage import CollectorHealth, SqliteRepository, make_engine
from marketpulse.storage.tables import ALL_TABLES, engine_heartbeat


@pytest.fixture
async def repo(tmp_path: Path) -> AsyncIterator[SqliteRepository]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'sub' / 'test.db'}"
    engine = make_engine(url)
    repository = SqliteRepository(engine, db_url=url)
    await repository.create_all()
    yield repository
    await repository.close()


async def test_sqlite_pragmas_applied(repo: SqliteRepository) -> None:
    async with repo.engine.connect() as conn:
        journal = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
        fk = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
    assert str(journal).lower() == "wal"
    assert fk == 1


async def test_create_all_creates_every_documented_table(repo: SqliteRepository) -> None:
    async with repo.engine.connect() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        names = {r[0] for r in rows}
    assert set(ALL_TABLES) <= names
    assert len(ALL_TABLES) == 32


async def test_heartbeat_roundtrip_and_clear(repo: SqliteRepository) -> None:
    assert await repo.read_heartbeat() is None
    ts = datetime(2026, 1, 1, 12, 0, 5, tzinfo=UTC)
    await repo.write_heartbeat(ts, "0.1.0")
    await repo.write_heartbeat(ts + timedelta(seconds=30), "0.1.0")  # upsert, tek satır
    hb = await repo.read_heartbeat()
    assert hb is not None
    assert hb.ts == ts + timedelta(seconds=30)
    assert hb.ts.tzinfo is not None
    await repo.clear_heartbeat()
    assert await repo.read_heartbeat() is None


async def test_utc_datetime_rejects_naive_on_bind(repo: SqliteRepository) -> None:
    async with repo.engine.begin() as conn:
        with pytest.raises(StatementError, match="naive"):
            await conn.execute(
                engine_heartbeat.insert().values(
                    id=1,
                    ts=datetime(2026, 1, 1),  # noqa: DTZ001 - kasıtlı naive
                    version="x",
                )
            )


async def test_collector_health_upsert_and_list(repo: SqliteRepository) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    await repo.upsert_collector_health(
        CollectorHealth(collector="rss", status="ok", last_success_at=now)
    )
    await repo.upsert_collector_health(
        CollectorHealth(
            collector="rss",
            status="degraded",
            last_error_at=now,
            last_error="boom",
            consecutive_failures=3,
        )
    )
    await repo.upsert_collector_health(CollectorHealth(collector="macro", status="disabled"))
    rows = await repo.list_collector_health()
    assert [r.collector for r in rows] == ["macro", "rss"]
    rss = rows[1]
    assert rss.status == "degraded"
    assert rss.consecutive_failures == 3
    assert rss.last_success_at is None  # upsert son durumu olduğu gibi yazar


async def test_outbox_emit_read_prune(repo: SqliteRepository) -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    assert await repo.outbox_max_id() == 0
    id1 = await repo.outbox_emit("health.changed", {"collector": "rss", "status": "ok"}, t0)
    id2 = await repo.outbox_emit("alert.created", {"id": 7, "when": t0}, t0 + timedelta(hours=2))
    assert id2 > id1
    assert await repo.outbox_max_id() == id2
    events = await repo.outbox_read_after(0)
    assert [e.topic for e in events] == ["health.changed", "alert.created"]
    assert events[1].payload["when"] == t0.isoformat()  # datetime default=str ile serileşir
    assert await repo.outbox_read_after(id1) == [events[1]]
    assert await repo.outbox_read_after(id2) == []
    pruned = await repo.outbox_prune(before=t0 + timedelta(hours=1))
    assert pruned == 1
    assert [e.id for e in await repo.outbox_read_after(0)] == [id2]


async def test_settings_roundtrip(repo: SqliteRepository) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert await repo.get_setting("symbols") is None
    await repo.set_setting("symbols", ["BTCUSDT"], now)
    await repo.set_setting("symbols", ["BTCUSDT", "ETHUSDT"], now)
    assert await repo.get_setting("symbols") == ["BTCUSDT", "ETHUSDT"]
    await repo.set_setting("budget", {"usd": 3.0}, now)
    assert await repo.get_setting("budget") == {"usd": 3.0}


async def test_db_size_reports_file_bytes(repo: SqliteRepository) -> None:
    size = await repo.db_size_bytes()
    assert size is not None
    assert size > 0
