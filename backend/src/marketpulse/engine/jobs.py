"""Duvar saatine hizalı iş döngüsü (ARCHITECTURE.md §5).

Her iş `every` aralığının epoch ızgarasındaki katlarında, `offset` kadar gecikmeyle tetiklenir.
Örnek: `every=15dk, offset=10sn` → 00:00:10, 00:15:10, 00:30:10, 00:45:10 (UTC).
APScheduler kullanılmaz: `FakeClock` ile test edilebilirlik ve tek dosyada görünürlük için.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.core.time import floor_to
from marketpulse.engine.health import HealthRegistry

JobFn = Callable[[datetime], Awaitable[None]]
Sleeper = Callable[[float], Awaitable[None]]

TICK_SEC = 1.0


@dataclass(frozen=True)
class Job:
    """Zamanlanmış iş. `fn` tetik zamanını (UTC) alır."""

    name: str
    every: timedelta
    fn: JobFn
    offset: timedelta = field(default_factory=lambda: timedelta(0))

    def next_run(self, after: datetime) -> datetime:
        """`after`'dan **kesinlikle sonraki** tetik zamanı."""
        grid = floor_to(after - self.offset, self.every) + self.offset
        while grid <= after:
            grid += self.every
        return grid


async def run_jobs(
    jobs: list[Job],
    stop: asyncio.Event,
    clock: Clock,
    health: HealthRegistry,
    *,
    sleep: Sleeper = asyncio.sleep,
    tick_sec: float = TICK_SEC,
) -> None:
    """İşleri zamanında çalıştırır. Bir işin hatası diğerlerini durdurmaz.

    Kaçırılan tetikler telafi edilmez: süreç uzun süre durduysa iş bir kez çalışır, geçmiş her
    tetik için tekrar tekrar değil.
    """
    schedule = {job.name: job.next_run(clock.now()) for job in jobs}
    while not stop.is_set():
        now = clock.now()
        for job in jobs:
            if schedule[job.name] > now:
                continue
            scheduled_at = schedule[job.name]
            schedule[job.name] = job.next_run(now)
            await _run_one(job, scheduled_at, health)
        wait = min((schedule[job.name] - clock.now()).total_seconds() for job in jobs)
        await _sleep_until(sleep, stop, min(max(wait, 0.0), tick_sec))


async def _run_one(job: Job, scheduled_at: datetime, health: HealthRegistry) -> None:
    try:
        await job.fn(scheduled_at)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        health.record_error(job.name, exc)
        logger.bind(job=job.name).warning("iş hata verdi: {err}", err=repr(exc))
    else:
        health.record_success(job.name)


async def _sleep_until(sleep: Sleeper, stop: asyncio.Event, seconds: float) -> None:
    if seconds <= 0:
        return
    if sleep is asyncio.sleep:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        return
    await sleep(seconds)
