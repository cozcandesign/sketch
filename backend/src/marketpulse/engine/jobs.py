"""Engine işleri.

Faz 0: sabit aralıklı döngü ve heartbeat. Faz 1 (F1-5): duvar saatine hizalı `Job`.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.engine.health import HealthRegistry
from marketpulse.storage.outbox import Outbox
from marketpulse.storage.repository import Repository


async def run_every(
    name: str,
    interval_sec: float,
    fn: Callable[[], Awaitable[None]],
    stop: asyncio.Event,
) -> None:
    """`fn`'i hemen ve sonra her `interval_sec`'te bir çalıştırır; `stop` ile biter.

    Hata yükseltir: çağıran supervisor yeniden başlatır ve sağlık kaydına işler.
    """
    while not stop.is_set():
        await fn()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_sec)
    logger.bind(job=name).debug("iş durdu")


def make_heartbeat(
    repo: Repository,
    health: HealthRegistry,
    outbox: Outbox,
    clock: Clock,
    version: str,
) -> Callable[[], Awaitable[None]]:
    """Heartbeat işi: `engine_heartbeat` satırını ve sağlık tablosunu tazeler."""

    async def _beat() -> None:
        await repo.write_heartbeat(clock.now(), version)
        health.record_success("engine")
        await health.flush(repo, outbox)

    return _beat
