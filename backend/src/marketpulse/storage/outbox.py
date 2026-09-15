"""Engine → api olay kanalı (ARCHITECTURE.md §2). Yazıcı: engine; okuyucu: api relay."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from marketpulse.core.clock import Clock
from marketpulse.storage.models import OutboxEvent
from marketpulse.storage.repository import Repository


class Outbox:
    """`events_outbox` tablosu üzerinde emit ve kuyruklu okuma."""

    def __init__(self, repo: Repository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    async def emit(self, topic: str, payload: dict[str, Any]) -> int:
        return await self._repo.outbox_emit(topic, payload, self._clock.now())

    async def tail(
        self,
        stop: asyncio.Event,
        *,
        poll_interval: float = 0.5,
        start_after: int | None = None,
    ) -> AsyncIterator[OutboxEvent]:
        """`start_after` sonrası olayları sırayla verir; yeni olay yoksa `poll_interval` bekler.

        `start_after=None` ise mevcut en büyük id'den başlar (geçmiş olaylar tekrar yayınlanmaz).
        """
        last_id = await self._repo.outbox_max_id() if start_after is None else start_after
        while not stop.is_set():
            events = await self._repo.outbox_read_after(last_id)
            if not events:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=poll_interval)
                continue
            for event in events:
                last_id = event.id
                yield event
