"""Türev piyasa REST toplayıcıları: funding, açık pozisyon, long/short, taker hacmi.

Dört ayrı collector, tek istemciyi paylaşır. Her biri ARCHITECTURE.md §4 tablosundaki ada sahiptir;
veri durumu şeridinde ayrı ayrı görünür, biri kopunca diğerleri çalışmaya devam eder.

**Collector'lar istisna sızdırmaz** (CLAUDE.md §6): hata sağlık kaydına yazılır, log düşer, döngü
devam eder. Bir uç nokta bozulursa ilgili veri seti "veri yok" olur; engine düşmez.
"""

from collections.abc import Sequence
from datetime import timedelta

from loguru import logger

from marketpulse.collectors.binance_futures import LONG_SHORT_KINDS, FuturesClient
from marketpulse.core.clock import Clock
from marketpulse.storage.repository import Repository

FUNDING_NAME = "funding"
OPEN_INTEREST_NAME = "open_interest"
LONG_SHORT_NAME = "long_short"
TAKER_VOLUME_NAME = "taker_volume"

# Binance `/futures/data/*` yalnızca son 30 gün verir (K5); 5 dk ızgarasında 30 gün = 8640 satır,
# tek istek 500 satır → sembol başına en fazla 18 istek.
DATA_PAGE_LIMIT = 500
HISTORY_DAYS = 30
FUNDING_HISTORY_DAYS = 90


class FundingCollector:
    """Gerçekleşmiş funding geçmişi (8 saatte bir) ve anlık funding göstergesi (dakikalık)."""

    name = FUNDING_NAME

    def __init__(
        self, client: FuturesClient, repo: Repository, clock: Clock, *, symbols: Sequence[str]
    ) -> None:
        self._client = client
        self._repo = repo
        self._clock = clock
        self._symbols = list(symbols)

    async def backfill(self) -> int:
        """Son 90 günün funding ödemeleri. Idempotent: aynı ödeme tekrar yazılmaz."""
        since = self._clock.now() - timedelta(days=FUNDING_HISTORY_DAYS)
        written = 0
        for symbol in self._symbols:
            rows = await self._client.funding_history(symbol, start=since)
            written += await self._repo.upsert_funding_rates(rows)
        logger.bind(collector=self.name).info("funding geçmişi: {n} satır", n=written)
        return written

    async def poll_live(self) -> int:
        """Anlık funding göstergesi; her sembol için bir satır."""
        now = self._clock.now()
        written = 0
        for symbol in self._symbols:
            live = await self._client.funding_live(symbol, now=now)
            written += await self._repo.upsert_funding_live([live])
        return written


class OpenInterestCollector:
    """Açık pozisyon: 5 dakikalık geçmiş ızgarası ve dakikalık anlık okuma."""

    name = OPEN_INTEREST_NAME

    def __init__(
        self, client: FuturesClient, repo: Repository, clock: Clock, *, symbols: Sequence[str]
    ) -> None:
        self._client = client
        self._repo = repo
        self._clock = clock
        self._symbols = list(symbols)

    async def backfill(self) -> int:
        written = 0
        for symbol in self._symbols:
            rows = await self._client.open_interest_history(symbol, limit=DATA_PAGE_LIMIT)
            written += await self._repo.upsert_open_interest(rows)
        logger.bind(collector=self.name).info("açık pozisyon geçmişi: {n} satır", n=written)
        return written

    async def poll_live(self) -> int:
        now = self._clock.now()
        written = 0
        for symbol in self._symbols:
            point = await self._client.open_interest_live(symbol, now=now)
            written += await self._repo.upsert_open_interest([point])
        return written


class LongShortCollector:
    """Üç long/short oranı: global hesap, top hesap, top pozisyon."""

    name = LONG_SHORT_NAME

    def __init__(self, client: FuturesClient, repo: Repository, *, symbols: Sequence[str]) -> None:
        self._client = client
        self._repo = repo
        self._symbols = list(symbols)

    async def poll(self) -> int:
        written = 0
        for symbol in self._symbols:
            for kind in LONG_SHORT_KINDS:
                rows = await self._client.long_short(symbol, kind, limit=DATA_PAGE_LIMIT)
                written += await self._repo.upsert_long_short(rows)
        return written


class TakerVolumeCollector:
    """5 dakikalık taker alış/satış hacmi; WS aggTrade koptuğunda CVD'nin yedeği."""

    name = TAKER_VOLUME_NAME

    def __init__(self, client: FuturesClient, repo: Repository, *, symbols: Sequence[str]) -> None:
        self._client = client
        self._repo = repo
        self._symbols = list(symbols)

    async def poll(self) -> int:
        written = 0
        for symbol in self._symbols:
            rows = await self._client.taker_volume(symbol, limit=DATA_PAGE_LIMIT)
            written += await self._repo.upsert_taker_volume(rows)
        return written
