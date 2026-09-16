from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.engine.health import HealthRegistry
from marketpulse.storage import Outbox, SqliteRepository, make_engine

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


def test_status_derivation_by_age(clock: FakeClock) -> None:
    h = HealthRegistry(clock)
    h.register("rss")
    assert h.status_of("rss") == "ok"  # henüz başlamadı, hata yok
    h.record_success("rss")
    assert h.status_of("rss") == "ok"
    clock.advance(timedelta(minutes=11))
    assert h.status_of("rss") == "degraded"
    clock.advance(timedelta(minutes=50))
    assert h.status_of("rss") == "down"
    h.record_success("rss")
    assert h.status_of("rss") == "ok"


def test_status_without_any_success(clock: FakeClock) -> None:
    h = HealthRegistry(clock)
    h.record_error("macro", RuntimeError("boom"))
    assert h.status_of("macro") == "degraded"
    h.record_error("macro", "x")
    h.record_error("macro", "y")
    assert h.status_of("macro") == "down"
    row = h.snapshot()[0]
    assert row.consecutive_failures == 3
    assert row.last_error == "y"


def test_forced_status_overrides(clock: FakeClock) -> None:
    h = HealthRegistry(clock)
    h.register("cryptopanic", status="disabled")
    h.record_success("cryptopanic")
    assert h.status_of("cryptopanic") == "disabled"
    h.set_status("cryptopanic", None)
    assert h.status_of("cryptopanic") == "ok"
    h.set_status("news_tier2", "budget_exhausted")
    assert h.status_of("news_tier2") == "budget_exhausted"


async def test_flush_writes_rows_and_emits_only_on_transition(
    clock: FakeClock, repo: SqliteRepository
) -> None:
    h = HealthRegistry(clock)
    outbox = Outbox(repo, clock)
    h.register("rss")
    h.record_success("rss")
    await h.flush(repo, outbox)
    await h.flush(repo, outbox)  # değişiklik yok → yeni olay yok
    events = await repo.outbox_read_after(0)
    assert [e.topic for e in events] == ["health.changed"]
    assert events[0].payload["status"] == "ok"
    clock.advance(timedelta(minutes=15))
    await h.flush(repo, outbox)
    events = await repo.outbox_read_after(0)
    assert [e.payload["status"] for e in events] == ["ok", "degraded"]
    rows = await repo.list_collector_health()
    assert rows[0].collector == "rss"
    assert rows[0].status == "degraded"


def test_a_four_hourly_job_is_not_reported_down_between_its_runs() -> None:
    """Periyodu bilinen iş kendi ritmine göre ölçülür (aksi halde 4 saatlik iş 3 saat kırmızı)."""
    clock = FakeClock(T0)
    registry = HealthRegistry(clock)
    registry.register("predict_24h", expected_interval=timedelta(hours=4))
    registry.record_success("predict_24h")

    clock.set(T0 + timedelta(hours=3))
    assert registry.status_of("predict_24h") == "ok"

    clock.set(T0 + timedelta(hours=7))  # 1.5 periyot geçti
    assert registry.status_of("predict_24h") == "degraded"

    clock.set(T0 + timedelta(hours=13))  # 3 periyodu aştı: gerçekten geç kalmış
    assert registry.status_of("predict_24h") == "down"


def test_a_collector_without_a_known_period_keeps_the_fixed_thresholds() -> None:
    clock = FakeClock(T0)
    registry = HealthRegistry(clock)
    registry.register("klines_ws")
    registry.record_success("klines_ws")

    clock.set(T0 + timedelta(minutes=30))
    assert registry.status_of("klines_ws") == "degraded"
    clock.set(T0 + timedelta(hours=2))
    assert registry.status_of("klines_ws") == "down"


def test_a_frequent_job_never_gets_a_shorter_threshold_than_the_default() -> None:
    """Dakikalık iş için eşik dakikalara inmez: tek bir gecikme kırmızı yapmamalı."""
    clock = FakeClock(T0)
    registry = HealthRegistry(clock)
    registry.register("resolve", expected_interval=timedelta(minutes=1))
    registry.record_success("resolve")

    clock.set(T0 + timedelta(minutes=5))
    assert registry.status_of("resolve") == "ok"
