"""Uzun ömürlü görevler için supervisor.

Düşen görev backoff ile yeniden başlar (ARCHITECTURE.md §17).
"""

import asyncio
import random
from collections.abc import Awaitable, Callable

from loguru import logger

from marketpulse.engine.health import HealthRegistry

BACKOFF_BASE_SEC = 1.0
BACKOFF_CAP_SEC = 300.0


def backoff_seconds(failures: int, *, rng: random.Random | None = None) -> float:
    """`min(300, 1 · 2^n) + jitter(0..1)`; `failures` ardışık hata sayısı (1'den başlar)."""
    n = max(0, failures - 1)
    base = min(BACKOFF_CAP_SEC, BACKOFF_BASE_SEC * (2.0**n))
    jitter = rng.random() if rng is not None else random.random()  # yayma; kriptografik değil
    return base + jitter


async def supervise(
    name: str,
    coro_factory: Callable[[], Awaitable[None]],
    stop: asyncio.Event,
    health: HealthRegistry,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """`coro_factory()` her çıkış veya hata sonrası yeniden çalıştırılır; `stop` set edilince biter.

    Görev normal döndüğünde (hata yok) supervisor da biter: sonsuz döngü görevin kendi işidir.
    """
    failures = 0
    while not stop.is_set():
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            health.record_error(name, exc)
            delay = backoff_seconds(failures)
            logger.bind(job=name).warning(
                "görev düştü, {delay:.1f} sn sonra yeniden başlar (ardışık hata: {n}): {err}",
                delay=delay,
                n=failures,
                err=repr(exc),
            )
            await sleep(delay)
        else:
            failures = 0
            return
