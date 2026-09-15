"""Engine süreci uçtan uca: mum → referans tahmin → çözümleme (ağ yok)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from marketpulse.config import Settings
from marketpulse.core.clock import FakeClock
from marketpulse.core.errors import EngineAlreadyRunningError
from marketpulse.core.types import Horizon, Interval
from marketpulse.engine.main import ensure_single_instance, run
from marketpulse.engine.predict import run_baseline_predictions
from marketpulse.storage import Candle, SqliteRepository, make_engine
from marketpulse.storage.migrate import schema_ready
from marketpulse.storage.outbox import Outbox
from marketpulse.tracking.ledger import Ledger
from marketpulse.tracking.resolver import Resolver

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'engine.db'}",
        heartbeat_interval_sec=0.05,
        heartbeat_stale_after_sec=60,
        symbols=["BTCUSDT"],
    )


@asynccontextmanager
async def _silent_ws(_url: str) -> AsyncIterator[AsyncIterator[str]]:
    """Mesaj göndermeyen sahte WS bağlantısı (testte ağ yok)."""

    async def stream() -> AsyncIterator[str]:
        await asyncio.sleep(3600)
        yield ""

    yield stream()


def m1_series(symbol: str, count: int, *, start: datetime = T0) -> list[Candle]:
    candles = []
    price = 100.0
    for index in range(count):
        open_time = start + index * Interval.M1.length
        previous = price
        price += 0.5 if index % 3 else -0.25
        candles.append(
            Candle(
                symbol=symbol,
                interval=Interval.M1,
                open_time=open_time,
                open=previous,
                high=max(previous, price),
                low=min(previous, price),
                close=price,
                volume=1.0,
                close_time=open_time + Interval.M1.length,
            )
        )
    return candles


async def test_single_instance_guard(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    await repo.create_all()
    clock = FakeClock(T0)
    await ensure_single_instance(repo, clock, 60)  # heartbeat yok → serbest
    await repo.write_heartbeat(clock.now(), "0.1.0")
    with pytest.raises(EngineAlreadyRunningError, match="zaten çalışıyor"):
        await ensure_single_instance(repo, clock, 60)
    clock.advance(timedelta(seconds=61))
    await ensure_single_instance(repo, clock, 60)  # bayat → serbest
    await repo.close()


async def test_run_writes_heartbeat_and_clears_on_stop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    await repo.create_all()
    stop = asyncio.Event()
    task = asyncio.create_task(
        run(
            settings,
            stop=stop,
            install_signal_handlers=False,
            schema_wait_sec=1,
            connect=_silent_ws,
            run_startup_tasks=False,
        )
    )
    for _ in range(200):
        await asyncio.sleep(0.02)
        if await repo.read_heartbeat() is not None:
            break
    assert await repo.read_heartbeat() is not None
    health = {h.collector for h in await repo.list_collector_health()}
    assert {"spot_klines", "klines_ws"} <= health
    stop.set()
    await asyncio.wait_for(task, timeout=10)
    assert await repo.read_heartbeat() is None
    await repo.close()


async def test_run_applies_migrations_when_schema_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    stop = asyncio.Event()
    engine = make_engine(settings.db_url)
    assert not await schema_ready(engine)
    task = asyncio.create_task(
        run(
            settings,
            stop=stop,
            install_signal_handlers=False,
            schema_wait_sec=0.1,
            connect=_silent_ws,
            run_startup_tasks=False,
        )
    )
    for _ in range(300):
        await asyncio.sleep(0.02)
        if await schema_ready(engine):
            break
    assert await schema_ready(engine)
    stop.set()
    await asyncio.wait_for(task, timeout=10)
    await engine.dispose()


async def test_prediction_to_resolution_flow(tmp_path: Path) -> None:
    """Mumlar → dört ufukta referans tahminler → ufuk dolunca çözümleme → metrik satırları."""
    settings = _settings(tmp_path)
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    await repo.create_all()
    clock = FakeClock(T0 + timedelta(hours=6))
    outbox = Outbox(repo, clock)
    ledger = Ledger(repo, clock, outbox)

    await repo.upsert_candles(m1_series("BTCUSDT", 400))
    as_of = T0 + timedelta(minutes=300)

    written = 0
    for horizon in Horizon:
        written += await run_baseline_predictions(
            repo, ledger, symbols=["BTCUSDT"], horizon=horizon, as_of=as_of
        )
    assert written == 8  # 4 ufuk × 2 referans tahminci

    predictions = await repo.list_predictions()
    assert {p.ensemble_version for p in predictions} == {
        "baseline-climatology-1",
        "baseline-momentum-1",
    }
    assert all(0.10 <= p.p_up <= 0.90 for p in predictions)  # K19 kırpması
    assert all(p.source == "baseline" for p in predictions)

    # 30 dakikalık ufuk dolar: hedef mumu ekle ve çözümle
    target = as_of + Horizon.H30M.length
    await repo.upsert_candles(
        [
            Candle(
                symbol="BTCUSDT",
                interval=Interval.M1,
                open_time=target - Interval.M1.length,
                open=100.0,
                high=200.0,
                low=100.0,
                close=200.0,
                volume=1.0,
                close_time=target,
            )
        ]
    )
    clock.set(target)
    stats = await Resolver(repo, clock, outbox).resolve_due()
    assert stats.resolved == 2  # yalnızca 30dk ufku

    rows = await repo.resolved_rows()
    assert len(rows) == 2
    assert all(r.y == 1 for r in rows)  # fiyat yükseldi
    topics = [e.topic for e in await repo.outbox_read_after(0)]
    assert topics.count("prediction.created") == 8
    assert topics.count("outcome.resolved") == 2
    await repo.close()
