"""Saklama (retention) işi. Süreler CLAUDE.md K21 ve ARCHITECTURE.md §6.6.

- Mumlar **kalıcıdır**: hiçbir zaman silinmez (K21).
- Order flow dakika özetleri ve ham likidasyonlar 90 gün tutulur; bu veriler Binance'te de
  saklanmadığı için silinen geri gelmez — süre bilinçli olarak uzun.
- `events_outbox` 24 saat: yalnızca api sürecine yayın kuyruğudur, geçmişi taşımaz.
- Haberler 180 gün: kendi fazında eklenir.
"""

from dataclasses import dataclass
from datetime import timedelta

from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.storage.repository import Repository

OUTBOX_TTL = timedelta(hours=24)
ORDERFLOW_TTL = timedelta(days=90)
LIQUIDATIONS_TTL = timedelta(days=90)


@dataclass(frozen=True)
class RetentionStats:
    outbox_pruned: int = 0
    orderflow_pruned: int = 0
    liquidations_pruned: int = 0

    @property
    def total(self) -> int:
        return self.outbox_pruned + self.orderflow_pruned + self.liquidations_pruned


async def run_retention(repo: Repository, clock: Clock) -> RetentionStats:
    now = clock.now()
    stats = RetentionStats(
        outbox_pruned=await repo.outbox_prune(now - OUTBOX_TTL),
        orderflow_pruned=await repo.delete_orderflow_before(now - ORDERFLOW_TTL),
        liquidations_pruned=await repo.delete_liquidations_before(now - LIQUIDATIONS_TTL),
    )
    if stats.total:
        logger.bind(job="retention").info(
            "temizlendi: outbox {o}, order flow {f}, likidasyon {l}",
            o=stats.outbox_pruned,
            f=stats.orderflow_pruned,
            l=stats.liquidations_pruned,
        )
    return stats
