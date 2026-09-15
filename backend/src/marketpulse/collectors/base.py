"""Collector sözleşmesi (ARCHITECTURE.md §4).

Kural: `run()` istisna sızdırmaz. Hata → sağlık kaydı + backoff + devam. Engine bir collector
yüzünden düşmez (CLAUDE.md §6).
"""

import asyncio
from typing import Protocol

from marketpulse.storage.models import CollectorHealth


class Collector(Protocol):
    name: str

    async def run(self, stop: asyncio.Event) -> None: ...

    def health(self) -> CollectorHealth: ...
