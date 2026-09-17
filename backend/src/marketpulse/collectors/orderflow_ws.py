"""Futures order flow akışı: `aggTrade`, `forceOrder`, `depth20@100ms` (ARCHITECTURE.md §4).

Mesajlar `OrderflowAggregator` içinde dakikalık kovalara toplanır; dakika kapandığında
`orderflow_1m` satırı yazılır. Likidasyonlar ayrıca ham satır olarak saklanır (kümeleme Faz 14).

Ham order book **saklanmaz** (K21): yalnızca top-20 dengesizliği ve spread özeti tutulur.
"""

import asyncio
import contextlib
import json
from collections.abc import Sequence
from datetime import timedelta
from typing import Any, Final

from loguru import logger

from marketpulse.collectors.orderflow_agg import OrderflowAggregator
from marketpulse.collectors.ws_stream import ConnectFactory, binance_connect, combined_url
from marketpulse.core.clock import Clock
from marketpulse.core.time import from_epoch_ms
from marketpulse.engine.health import HealthRegistry
from marketpulse.storage.models import Liquidation
from marketpulse.storage.repository import Repository

COLLECTOR_NAME: Final = "ws_orderflow"
PLANNED_RECONNECT: Final = timedelta(hours=23)
FLUSH_INTERVAL_SEC: Final = 5.0
DEPTH_STREAM: Final = "depth20@100ms"


def streams_for(symbols: Sequence[str]) -> list[str]:
    """Her sembol için üç akış: işlemler, zorunlu kapatmalar, kitap anlık görüntüsü."""
    streams: list[str] = []
    for symbol in symbols:
        lower = symbol.lower()
        streams.extend([f"{lower}@aggTrade", f"{lower}@forceOrder", f"{lower}@{DEPTH_STREAM}"])
    return streams


def parse_liquidation(payload: dict[str, Any]) -> Liquidation | None:
    """`forceOrder` mesajı → likidasyon satırı.

    Binance zorunlu kapatmayı **emir yönüyle** verir: `S=SELL` bir LONG pozisyonun kapatıldığı
    anlamına gelir (uzun pozisyon satılarak kapanır), `S=BUY` ise SHORT kapanışıdır.
    """
    order = payload.get("o")
    if not isinstance(order, dict):
        return None
    filled = float(order.get("z") or order.get("q") or 0.0)
    price = float(order.get("ap") or order.get("p") or 0.0)
    if filled <= 0 or price <= 0:
        return None
    return Liquidation(
        symbol=str(order["s"]),
        ts=from_epoch_ms(int(order.get("T") or payload["E"])),
        side="long" if str(order.get("S", "")).upper() == "SELL" else "short",
        qty=filled,
        price=price,
        usd=filled * price,
    )


def parse_levels(raw: Any) -> list[tuple[float, float]]:
    """`[["fiyat","miktar"], ...]` → sayısal çiftler; bozuk satırlar atlanır."""
    levels: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        return levels
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            with contextlib.suppress(TypeError, ValueError):
                levels.append((float(item[0]), float(item[1])))
    return levels


class OrderflowWsCollector:
    """Üç futures akışını dinler, dakikalık özetleri ve likidasyonları yazar."""

    name = COLLECTOR_NAME

    def __init__(
        self,
        ws_base_url: str,
        repo: Repository,
        clock: Clock,
        health: HealthRegistry,
        *,
        symbols: Sequence[str],
        connect: ConnectFactory = binance_connect,
        planned_reconnect: timedelta = PLANNED_RECONNECT,
        flush_interval_sec: float = FLUSH_INTERVAL_SEC,
    ) -> None:
        self._url = combined_url(ws_base_url, streams_for(symbols))
        self._repo = repo
        self._clock = clock
        self._health = health
        self._connect = connect
        self._planned_reconnect = planned_reconnect
        self._flush_interval_sec = flush_interval_sec
        self._agg = OrderflowAggregator()
        self._last_flush = clock.now()

    @property
    def aggregator(self) -> OrderflowAggregator:
        return self._agg

    async def run(self, stop: asyncio.Event) -> None:
        """Bağlantıyı açar. Kopunca kapsama sayacı durur; supervisor yeniden başlatır."""
        deadline = self._clock.now() + self._planned_reconnect
        logger.bind(collector=self.name).info("order flow akışına bağlanılıyor")
        try:
            async with self._connect(self._url) as messages:
                self._agg.mark_connected(self._clock.now())
                self._health.record_success(self.name)
                async for raw in messages:
                    if stop.is_set():
                        return
                    await self.handle_message(raw)
                    await self._maybe_flush()
                    if self._clock.now() >= deadline:
                        logger.bind(collector=self.name).info("planlı yeniden bağlanma")
                        return
        finally:
            self._agg.mark_disconnected(self._clock.now())
            await self.flush()

    async def flush(self) -> int:
        """Kapanmış dakikaları yazar. Yazılan satır sayısını döner."""
        rows = self._agg.take_closed(self._clock.now())
        if not rows:
            return 0
        await self._repo.upsert_orderflow(rows)
        return len(rows)

    async def _maybe_flush(self) -> None:
        now = self._clock.now()
        if (now - self._last_flush).total_seconds() < self._flush_interval_sec:
            return
        self._last_flush = now
        await self.flush()

    async def handle_message(self, raw: str) -> None:
        """Tek mesajı işler. Bozuk mesaj akışı durdurmaz; testler bu yolu doğrudan çağırır."""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.bind(collector=self.name).warning("bozuk mesaj atlandı")
            return
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            return
        try:
            await self._dispatch(data, stream=str(payload.get("stream", "")))
        except (KeyError, ValueError, TypeError) as exc:
            # Sessizce yutulmaz: Binance bir alan adını değiştirirse akış "çalışıyor" görünüp
            # sıfır hacim yazardı; bileşen kendiliğinden kaybolurdu. Görünür olsun (CLAUDE.md §2).
            self._health.record_error(self.name, exc)
            logger.bind(collector=self.name, event=str(data.get("e", "?"))).warning(
                "mesaj ayrıştırılamadı: {e}", e=repr(exc)
            )
            return
        self._health.record_success(self.name)

    async def _dispatch(self, data: dict[str, Any], *, stream: str) -> None:
        event = data.get("e")
        if event == "aggTrade":
            self._agg.add_trade(
                str(data["s"]),
                from_epoch_ms(int(data["T"])),
                qty=float(data["q"]),
                is_buyer_maker=bool(data["m"]),
            )
            return
        if event == "forceOrder":
            liquidation = parse_liquidation(data)
            if liquidation is not None:
                self._agg.add_liquidation(liquidation)
                await self._repo.insert_liquidations([liquidation])
            return
        self._handle_book(data, stream=stream)

    def _handle_book(self, data: dict[str, Any], *, stream: str) -> None:
        """Kısmi derinlik mesajı. Sembol bazen yalnızca stream adında gelir (spot biçimi)."""
        bids = parse_levels(data.get("b", data.get("bids")))
        asks = parse_levels(data.get("a", data.get("asks")))
        if not bids or not asks:
            return
        symbol = str(data.get("s") or stream.split("@", maxsplit=1)[0]).upper()
        if not symbol:
            return
        timestamp = data.get("T") or data.get("E")
        ts = from_epoch_ms(int(timestamp)) if timestamp else self._clock.now()
        self._agg.add_book(symbol, ts, bids=bids, asks=asks)
