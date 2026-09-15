import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marketpulse.config import Settings
from marketpulse.core.clock import FakeClock
from marketpulse.core.errors import EngineAlreadyRunningError
from marketpulse.engine.main import ensure_single_instance, run
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.migrate import schema_ready


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'engine.db'}",
        heartbeat_interval_sec=0.05,
        heartbeat_stale_after_sec=60,
    )


async def test_single_instance_guard(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    await repo.create_all()
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    await ensure_single_instance(repo, clock, 60)  # heartbeat yok → serbest
    await repo.write_heartbeat(clock.now(), "0.1.0")
    with pytest.raises(EngineAlreadyRunningError, match="zaten çalışıyor"):
        await ensure_single_instance(repo, clock, 60)
    clock.advance(timedelta(seconds=61))
    await ensure_single_instance(repo, clock, 60)  # bayat → serbest
    await repo.close()


async def test_run_writes_heartbeat_then_clears_on_stop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    await repo.create_all()
    stop = asyncio.Event()
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    task = asyncio.create_task(
        run(settings, clock=clock, stop=stop, install_signal_handlers=False, schema_wait_sec=1)
    )
    for _ in range(100):
        await asyncio.sleep(0.02)
        if await repo.read_heartbeat() is not None:
            break
    heartbeat = await repo.read_heartbeat()
    assert heartbeat is not None
    assert heartbeat.ts == clock.now()
    # Engine kendisi collector değildir: Faz 0'da sağlık tablosu ve outbox boş kalır.
    assert await repo.list_collector_health() == []
    assert await repo.outbox_read_after(0) == []
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert await repo.read_heartbeat() is None  # temiz kapanış heartbeat'i siler
    await repo.close()


async def test_run_applies_migrations_when_schema_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    stop = asyncio.Event()
    engine = make_engine(settings.db_url)
    assert not await schema_ready(engine)
    task = asyncio.create_task(
        run(settings, stop=stop, install_signal_handlers=False, schema_wait_sec=0.1)
    )
    for _ in range(200):
        await asyncio.sleep(0.02)
        if await schema_ready(engine):
            break
    assert await schema_ready(engine)
    stop.set()
    await asyncio.wait_for(task, timeout=10)
    await engine.dispose()
