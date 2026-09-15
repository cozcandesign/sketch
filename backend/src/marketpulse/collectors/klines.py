"""Spot mum (kline) toplayıcısı: REST ile geçmiş doldurma ve boşluk denetimi.

Canlı akış `collectors/klines_ws.py` içindedir; bu modül yalnızca REST tarafıdır.
Yalnızca kapanmış mumlar yazılır (ARCHITECTURE.md §7).
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from loguru import logger

from marketpulse.collectors.binance_client import MAX_KLINES_LIMIT, BinanceClient
from marketpulse.core.clock import Clock
from marketpulse.core.time import floor_to
from marketpulse.core.types import Interval
from marketpulse.storage.repository import Repository

COLLECTOR_NAME = "spot_klines"

# Geçmiş doldurma pencereleri (ARCHITECTURE.md §7 geriye bakış pencereleriyle uyumlu)
BACKFILL_LOOKBACK: dict[Interval, timedelta] = {
    Interval.M1: timedelta(days=2),
    Interval.M5: timedelta(days=7),
    Interval.M15: timedelta(days=30),
    Interval.H1: timedelta(days=90),
    Interval.H4: timedelta(days=365),
    Interval.D1: timedelta(days=730),
}
GAP_CHECK_LOOKBACK: dict[Interval, timedelta] = {
    Interval.M1: timedelta(hours=6),
    Interval.M5: timedelta(hours=12),
    Interval.M15: timedelta(days=1),
    Interval.H1: timedelta(days=3),
    Interval.H4: timedelta(days=10),
    Interval.D1: timedelta(days=30),
}


class KlinesCollector:
    """REST tarafı: açılışta geçmiş doldurma, sonra periyodik boşluk denetimi."""

    name = COLLECTOR_NAME

    def __init__(
        self,
        client: BinanceClient,
        repo: Repository,
        clock: Clock,
        *,
        symbols: Sequence[str],
        intervals: Sequence[Interval],
        page_limit: int = MAX_KLINES_LIMIT,
    ) -> None:
        self._client = client
        self._repo = repo
        self._clock = clock
        self._symbols = list(symbols)
        self._intervals = list(intervals)
        self._page_limit = min(page_limit, MAX_KLINES_LIMIT)

    async def backfill(self, *, lookback: dict[Interval, timedelta] | None = None) -> int:
        """Her sembol ve zaman dilimi için geçmişi doldurur. Yazılan mum sayısını döner."""
        windows = lookback or BACKFILL_LOOKBACK
        now = self._clock.now()
        total = 0
        for symbol in self._symbols:
            for interval in self._intervals:
                since = floor_to(now - windows[interval], interval.length)
                total += await self._fetch_range(symbol, interval, since, now)
        logger.bind(collector=self.name).info("geçmiş doldurma bitti: {n} mum", n=total)
        return total

    async def fill_gaps(self) -> int:
        """Son dönemdeki eksik mumları REST ile tamamlar (WS kesintileri için)."""
        now = self._clock.now()
        total = 0
        for symbol in self._symbols:
            for interval in self._intervals:
                since = floor_to(now - GAP_CHECK_LOOKBACK[interval], interval.length)
                until = floor_to(now, interval.length)  # oluşmakta olan mum hariç
                gaps = await self._repo.find_candle_gaps(symbol, interval, since=since, until=until)
                for gap in gaps:
                    total += await self._fetch_range(symbol, interval, gap.start, gap.end)
        if total:
            logger.bind(collector=self.name).info("boşluk doldurma: {n} mum", n=total)
        return total

    async def fetch_candle(self, symbol: str, interval: Interval, close_time: datetime) -> bool:
        """Tek bir mumu REST ile çeker (resolver'ın gecikmiş mum için kullandığı yol)."""
        start = close_time - interval.length
        candles = await self._client.klines(symbol, interval, start=start, end=close_time, limit=2)
        closed = [c for c in candles if c.close_time <= close_time]
        if not closed:
            return False
        await self._repo.upsert_candles(closed)
        return True

    async def _fetch_range(
        self, symbol: str, interval: Interval, since: datetime, until: datetime
    ) -> int:
        """[since, until) aralığını sayfalayarak çeker ve yazar."""
        written = 0
        cursor = since
        while cursor < until:
            candles = await self._client.klines(
                symbol, interval, start=cursor, end=until, limit=self._page_limit
            )
            closed = [c for c in candles if c.close_time <= until]
            if not closed:
                break
            written += await self._repo.upsert_candles(closed)
            next_cursor = closed[-1].open_time + interval.length
            if next_cursor <= cursor:  # ilerleme yoksa sonsuz döngüyü kes
                break
            cursor = next_cursor
            if len(candles) < self._page_limit:
                break  # sayfa dolmadıysa aralıkta başka mum yok
        return written
