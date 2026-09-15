from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.engine.health import HealthRegistry
from marketpulse.storage import Outbox, SqliteRepository, make_engine


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))


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
