import asyncio
import random
from datetime import UTC, datetime

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.engine.health import HealthRegistry
from marketpulse.engine.supervisor import BACKOFF_CAP_SEC, backoff_seconds, supervise


def test_backoff_doubles_and_caps() -> None:
    rng = random.Random(0)
    values = [backoff_seconds(n, rng=rng) for n in range(1, 12)]
    bases = [v - (v % 1) for v in values]
    assert bases[:5] == [1, 2, 4, 8, 16]
    assert all(v <= BACKOFF_CAP_SEC + 1 for v in values)
    assert bases[-1] == BACKOFF_CAP_SEC


async def test_supervise_restarts_until_success_and_records_errors() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    health = HealthRegistry(clock)
    stop = asyncio.Event()
    calls = 0
    slept: list[float] = []

    async def flaky() -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            msg = f"deneme {calls}"
            raise RuntimeError(msg)

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    await supervise("flaky", flaky, stop, health, sleep=fake_sleep)
    assert calls == 3
    assert len(slept) == 2
    assert 1 <= slept[0] < 2
    assert 2 <= slept[1] < 3
    row = next(r for r in health.snapshot() if r.collector == "flaky")
    assert row.consecutive_failures == 2
    assert row.last_error is not None
    assert "deneme 2" in row.last_error


async def test_supervise_stops_when_event_set() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    health = HealthRegistry(clock)
    stop = asyncio.Event()

    async def always_fails() -> None:
        stop.set()
        raise RuntimeError("x")

    async def fake_sleep(_: float) -> None:
        return None

    await supervise("f", always_fails, stop, health, sleep=fake_sleep)
    assert health.status_of("f") == "degraded"


async def test_supervise_propagates_cancellation() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    health = HealthRegistry(clock)
    stop = asyncio.Event()

    async def forever() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(supervise("forever", forever, stop, health))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
