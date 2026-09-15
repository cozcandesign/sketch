"""Binance ağırlık (weight) limiti yönetimi (ARCHITECTURE.md §4).

Binance istekleri "weight" ile sayar ve dakikalık bir tavan uygular. Bu sınıf kullanılan ağırlığı
pencere bazında takip eder, tavana yaklaşınca istekleri seyreltir, 429/418 sonrası bekler.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.core.time import floor_to

DEFAULT_WEIGHT_LIMIT = 6000
DEFAULT_WINDOW = timedelta(minutes=1)
SOFT_RATIO = 0.7
SOFT_DELAY_SEC = 0.25

Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class WeightLimit:
    """exchangeInfo'dan okunan REQUEST_WEIGHT limiti."""

    limit: int
    window: timedelta


class RateLimiter:
    """Dakikalık ağırlık penceresi. Tek örnek bir Binance tabanı (spot / futures) içindir."""

    def __init__(
        self,
        clock: Clock,
        *,
        limit: int = DEFAULT_WEIGHT_LIMIT,
        window: timedelta = DEFAULT_WINDOW,
        soft_ratio: float = SOFT_RATIO,
        sleep: Sleeper = asyncio.sleep,
        name: str = "binance",
    ) -> None:
        self._clock = clock
        self._limit = limit
        self._window = window
        self._soft_ratio = soft_ratio
        self._sleep = sleep
        self._name = name
        self._window_start = floor_to(clock.now(), window)
        self._used = 0
        self._blocked_until: datetime | None = None

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def used(self) -> int:
        self._roll_window(self._clock.now())
        return self._used

    @property
    def blocked_until(self) -> datetime | None:
        return self._blocked_until

    def apply_limit(self, weight_limit: WeightLimit) -> None:
        """exchangeInfo'dan gelen gerçek limiti uygular."""
        self._limit = weight_limit.limit
        self._window = weight_limit.window
        logger.bind(collector=self._name).debug(
            "ağırlık limiti güncellendi: {limit}/{window}s",
            limit=weight_limit.limit,
            window=int(weight_limit.window.total_seconds()),
        )

    def observe_used_weight(self, used: int) -> None:
        """`X-MBX-USED-WEIGHT-1M` başlığıyla senkron. Sunucunun sayacı bizimkinden önceliklidir."""
        self._roll_window(self._clock.now())
        self._used = max(self._used, used)

    def block_for(self, seconds: float) -> None:
        """429 `Retry-After` veya 418 IP ban: verilen süre boyunca istek gönderilmez."""
        until = self._clock.now() + timedelta(seconds=seconds)
        if self._blocked_until is None or until > self._blocked_until:
            self._blocked_until = until
        logger.bind(collector=self._name).warning(
            "istekler {s:.0f} sn durduruldu (429/418)", s=seconds
        )

    async def acquire(self, weight: int) -> None:
        """İstek için yer açar; gerekirse pencere sonuna kadar bekler."""
        while True:
            now = self._clock.now()
            if self._blocked_until is not None:
                if now < self._blocked_until:
                    await self._sleep((self._blocked_until - now).total_seconds())
                    continue
                self._blocked_until = None
            self._roll_window(now)
            if self._used + weight > self._limit:
                await self._sleep(self._seconds_to_next_window(now))
                continue
            if self._used + weight > self._limit * self._soft_ratio:
                await self._sleep(SOFT_DELAY_SEC)  # tavana yaklaşınca seyrelt
            self._used += weight
            return

    def _roll_window(self, now: datetime) -> None:
        current = floor_to(now, self._window)
        if current != self._window_start:
            self._window_start = current
            self._used = 0

    def _seconds_to_next_window(self, now: datetime) -> float:
        return max(0.01, (self._window_start + self._window - now).total_seconds())
