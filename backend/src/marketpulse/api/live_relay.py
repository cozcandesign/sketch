"""Canlı fiyat aktarımı (ARCHITECTURE.md §2).

Api süreci Binance spot `miniTicker` akışına kendisi bağlanır ve `price.{symbol}` konusuna
yayınlar. Fiyat DB'ye yazılmaz: saniyelik veri kalıcı değildir. Bağlantı koparsa istemciye
`stale=true` gider; arayüz "canlı değil" gösterir.
"""

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from marketpulse.api.ws import WsHub
from marketpulse.collectors.ws_stream import ConnectFactory, binance_connect, combined_url
from marketpulse.core.clock import Clock
from marketpulse.core.time import from_epoch_ms

THROTTLE_SEC = 0.5
RECONNECT_BASE_SEC = 1.0
RECONNECT_CAP_SEC = 30.0


@dataclass
class LiveState:
    """Sağlık ucunun gösterdiği canlı fiyat durumu."""

    connected: bool = False
    last_message_at: datetime | None = None
    messages: int = 0
    reconnects: int = 0
    last_prices: dict[str, float] = field(default_factory=dict)


def parse_mini_ticker(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """`24hrMiniTicker` mesajını (sembol, veri) çiftine çevirir; başka mesajlarda None."""
    data = payload.get("data", payload)
    if data.get("e") != "24hrMiniTicker":
        return None
    last = float(data["c"])
    open_price = float(data["o"])
    change = (last / open_price - 1.0) if open_price else None
    return str(data["s"]), {
        "price": last,
        "change24h": change,
        "high24h": float(data["h"]),
        "low24h": float(data["l"]),
        "ts": from_epoch_ms(int(data["E"])).isoformat(),
        "stale": False,
    }


class LiveRelay:
    """miniTicker akışını WS istemcilerine taşır; kopunca üstel backoff ile yeniden bağlanır."""

    def __init__(
        self,
        ws_base_url: str,
        symbols: list[str],
        hub: WsHub,
        clock: Clock,
        state: LiveState,
        *,
        connect: ConnectFactory = binance_connect,
        throttle_sec: float = THROTTLE_SEC,
    ) -> None:
        self._url = combined_url(ws_base_url, [f"{s.lower()}@miniTicker" for s in symbols])
        self._symbols = symbols
        self._hub = hub
        self._clock = clock
        self._state = state
        self._connect = connect
        self._throttle_sec = throttle_sec
        self._last_sent: dict[str, float] = {}

    async def run(self, stop: asyncio.Event) -> None:
        """`stop` set edilene kadar bağlı kalmaya çalışır. İstisna sızdırmaz."""
        attempt = 0
        while not stop.is_set():
            try:
                async with self._connect(self._url) as messages:
                    self._state.connected = True
                    attempt = 0
                    logger.bind(process="api").info("canlı fiyat akışına bağlanıldı")
                    async for raw in messages:
                        if stop.is_set():
                            break
                        await self._handle(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.bind(process="api").warning("canlı fiyat akışı koptu: {e}", e=repr(exc))
            finally:
                self._state.connected = False
            if stop.is_set():
                return
            self._state.reconnects += 1
            await self._mark_stale()
            delay = min(RECONNECT_CAP_SEC, RECONNECT_BASE_SEC * (2**attempt))
            attempt += 1
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)

    async def _handle(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        parsed = parse_mini_ticker(payload)
        if parsed is None:
            return
        symbol, data = parsed
        now = self._clock.now()
        last_sent = self._last_sent.get(symbol)
        timestamp = now.timestamp()
        if last_sent is not None and timestamp - last_sent < self._throttle_sec:
            return  # saniyede en fazla iki mesaj
        self._last_sent[symbol] = timestamp
        self._state.messages += 1
        self._state.last_message_at = now
        self._state.last_prices[symbol] = data["price"]
        await self._hub.broadcast(f"price.{symbol}", data, now)

    async def _mark_stale(self) -> None:
        now = self._clock.now()
        for symbol in self._symbols:
            await self._hub.broadcast(
                f"price.{symbol}",
                {"price": self._state.last_prices.get(symbol), "stale": True},
                now,
            )
