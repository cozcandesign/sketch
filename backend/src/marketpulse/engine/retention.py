"""Saklama (retention) işi. Süreler CLAUDE.md K21 ve ARCHITECTURE.md §6.6.

Faz 1 kapsamı: yalnızca `events_outbox`. Mumlar kalıcıdır (K21); order flow ve haber tabloları
kendi fazlarında eklenir.
"""

from dataclasses import dataclass
from datetime import timedelta

from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.storage.repository import Repository

OUTBOX_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class RetentionStats:
    outbox_pruned: int = 0


async def run_retention(repo: Repository, clock: Clock) -> RetentionStats:
    pruned = await repo.outbox_prune(clock.now() - OUTBOX_TTL)
    if pruned:
        logger.bind(job="retention").info("outbox temizlendi: {n} satır", n=pruned)
    return RetentionStats(outbox_pruned=pruned)
