import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.storage import Outbox, SqliteRepository, make_engine


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


async def test_tail_yields_new_events_and_stops(repo: SqliteRepository) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    outbox = Outbox(repo, clock)
    old_id = await outbox.emit("old", {})  # tail başlamadan önce: yayınlanmamalı
    await outbox.emit("a", {"n": 1})
    await outbox.emit("b", {"n": 2})
    stop = asyncio.Event()
    received: list[str] = []

    async def consume() -> None:
        # Başlangıç noktası açıkça verilir: "tüketici zamanında başladı mı" yarışı olmasın.
        async for event in outbox.tail(stop, poll_interval=0.01, start_after=old_id):
            received.append(event.topic)
            if len(received) == 2:
                stop.set()

    await asyncio.wait_for(asyncio.create_task(consume()), timeout=5)
    assert received == ["a", "b"]


async def test_tail_can_replay_from_explicit_id(repo: SqliteRepository) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    outbox = Outbox(repo, clock)
    first = await outbox.emit("x", {})
    await outbox.emit("y", {})
    stop = asyncio.Event()
    topics: list[str] = []
    async for event in outbox.tail(stop, poll_interval=0.01, start_after=first):
        topics.append(event.topic)
        stop.set()
    assert topics == ["y"]
