import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.engine.health import HealthRegistry
from marketpulse.engine.jobs import Job, run_jobs

T0 = datetime(2026, 1, 1, 12, 7, 33, tzinfo=UTC)


async def _noop(_scheduled: datetime) -> None:
    return None


@pytest.mark.parametrize(
    ("every", "offset", "after", "expected"),
    [
        (
            timedelta(minutes=15),
            timedelta(seconds=10),
            T0,
            datetime(2026, 1, 1, 12, 15, 10, tzinfo=UTC),
        ),
        (
            timedelta(minutes=30),
            timedelta(seconds=10),
            T0,
            datetime(2026, 1, 1, 12, 30, 10, tzinfo=UTC),
        ),
        (
            timedelta(hours=1),
            timedelta(seconds=10),
            T0,
            datetime(2026, 1, 1, 13, 0, 10, tzinfo=UTC),
        ),
        (
            timedelta(hours=4),
            timedelta(seconds=10),
            T0,
            datetime(2026, 1, 1, 16, 0, 10, tzinfo=UTC),
        ),
        (timedelta(days=1), timedelta(hours=3), T0, datetime(2026, 1, 2, 3, 0, tzinfo=UTC)),
    ],
)
def test_next_run_is_aligned_to_wall_clock(
    every: timedelta, offset: timedelta, after: datetime, expected: datetime
) -> None:
    job = Job("x", every, _noop, offset=offset)
    assert job.next_run(after) == expected


def test_next_run_is_strictly_after_given_time() -> None:
    job = Job("x", timedelta(minutes=15), _noop, offset=timedelta(seconds=10))
    exact = datetime(2026, 1, 1, 12, 15, 10, tzinfo=UTC)
    assert job.next_run(exact) == exact + timedelta(minutes=15)


async def test_run_jobs_fires_at_trigger_time_and_passes_scheduled_time() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 11, 59, 55, tzinfo=UTC))
    health = HealthRegistry(clock)
    stop = asyncio.Event()
    fired: list[datetime] = []

    async def record(scheduled: datetime) -> None:
        fired.append(scheduled)
        if len(fired) == 3:
            stop.set()

    async def sleep(seconds: float) -> None:
        clock.advance(timedelta(seconds=seconds))

    job = Job("predict", timedelta(minutes=15), record, offset=timedelta(seconds=10))
    await run_jobs([job], stop, clock, health, sleep=sleep, tick_sec=30.0)

    assert fired == [
        datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 15, 10, tzinfo=UTC),
        datetime(2026, 1, 1, 12, 30, 10, tzinfo=UTC),
    ]
    assert health.status_of("predict") == "ok"


async def test_missed_triggers_fire_once_not_repeatedly() -> None:
    """Süreç uzun süre durduysa geçmiş her tetik için tekrar tekrar çalışılmaz."""
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
    health = HealthRegistry(clock)
    stop = asyncio.Event()
    fired: list[datetime] = []

    async def record(scheduled: datetime) -> None:
        fired.append(scheduled)
        clock.advance(timedelta(hours=2))  # iş uzun sürdü: 8 tetik kaçtı
        stop.set()

    async def sleep(seconds: float) -> None:
        clock.advance(timedelta(seconds=seconds))

    await run_jobs(
        [Job("predict", timedelta(minutes=15), record)], stop, clock, health, sleep=sleep
    )
    assert len(fired) == 1


async def test_job_error_is_recorded_and_others_keep_running() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 11, 59, 59, tzinfo=UTC))
    health = HealthRegistry(clock)
    stop = asyncio.Event()
    good: list[datetime] = []

    async def boom(_scheduled: datetime) -> None:
        raise RuntimeError("iş patladı")

    async def fine(scheduled: datetime) -> None:
        good.append(scheduled)
        stop.set()

    async def sleep(seconds: float) -> None:
        clock.advance(timedelta(seconds=seconds))

    await run_jobs(
        [Job("bad", timedelta(minutes=1), boom), Job("good", timedelta(minutes=1), fine)],
        stop,
        clock,
        health,
        sleep=sleep,
    )
    assert len(good) == 1
    assert health.status_of("bad") == "degraded"
    row = next(r for r in health.snapshot() if r.collector == "bad")
    assert row.last_error is not None
    assert "iş patladı" in row.last_error
