"""Canlı mum akışı: `<symbol>@kline_1m` combined stream.

Yalnızca kapanmış mumlar (`k.x == true`) yazılır. Binance bağlantıyı 24 saatte kapatır; biz
23. saatte planlı olarak yenileriz (ARCHITECTURE.md §4).
"""

import asyncio
import contextlib
import json
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from loguru import logger

from marketpulse.collectors.ws_stream import ConnectFactory, binance_connect, combined_url
from marketpulse.core.clock import Clock
from marketpulse.core.time import from_epoch_ms
from marketpulse.core.types import Interval
from marketpulse.engine.health import HealthRegistry
from marketpulse.storage.models import Candle
from marketpulse.storage.repository import Repository

COLLECTOR_NAME = "klines_ws"
PLANNED_RECONNECT = timedelta(hours=23)


def parse_ws_kline(payload: dict[str, Any]) -> Candle | None:
    """Combined stream mesajını muma çevirir. Mum kapanmadıysa None döner."""
    data = payload.get("data", payload)
    if data.get("e") != "kline":
        return None
    kline = data["k"]
    if not kline.get("x"):
        return None  # oluşmakta olan mum: asla yazılmaz (look-ahead koruması)
    interval = Interval(kline["i"])
    open_time = from_epoch_ms(int(kline["t"]))
    return Candle(
        symbol=str(kline["s"]),
        interval=interval,
        open_time=open_time,
        open=float(kline["o"]),
        high=float(kline["h"]),
        low=float(kline["l"]),
        close=float(kline["c"]),
        volume=float(kline["v"]),
        quote_volume=float(kline["q"]),
        trades=int(kline["n"]),
        taker_buy_base=float(kline["V"]),
        close_time=open_time + interval.length,
    )


class KlinesWsCollector:
    """1 dakikalık mumları canlı yazar; bağlantı koparsa dışarıdaki supervisor yeniden başlatır."""

    name = COLLECTOR_NAME

    def __init__(
        self,
        ws_base_url: str,
        repo: Repository,
        clock: Clock,
        health: HealthRegistry,
        *,
        symbols: Sequence[str],
        interval: Interval = Interval.M1,
        connect: ConnectFactory = binance_connect,
        planned_reconnect: timedelta = PLANNED_RECONNECT,
    ) -> None:
        self._url = combined_url(
            ws_base_url, [f"{s.lower()}@kline_{interval.value}" for s in symbols]
        )
        self._repo = repo
        self._clock = clock
        self._health = health
        self._connect = connect
        self._planned_reconnect = planned_reconnect
        self._written = 0

    @property
    def written(self) -> int:
        return self._written

    async def run(self, stop: asyncio.Event) -> None:
        """Bağlantıyı açar ve mesajları işler. `stop` ile ya da planlı yenileme ile döner."""
        deadline = self._clock.now() + self._planned_reconnect
        logger.bind(collector=self.name).info("canlı mum akışına bağlanılıyor")
        async with self._connect(self._url) as messages:
            self._health.record_success(self.name)
            async for raw in messages:
                if stop.is_set():
                    return
                await self._handle(raw)
                if self._clock.now() >= deadline:
                    logger.bind(collector=self.name).info("planlı yeniden bağlanma")
                    return

    async def _handle(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.bind(collector=self.name).warning("bozuk mesaj atlandı")
            return
        with contextlib.suppress(KeyError, ValueError, TypeError):
            candle = parse_ws_kline(payload)
            if candle is None:
                return
            await self._repo.upsert_candles([candle])
            self._written += 1
            self._health.record_success(self.name)
