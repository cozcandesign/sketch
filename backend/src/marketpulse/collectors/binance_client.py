"""Binance public REST istemcisi (ARCHITECTURE.md §4).

Yalnızca public endpoint'ler; API anahtarı yok, imzalı istek yok (CLAUDE.md §1).
Ağırlık limiti `RateLimiter` ile, geçici hatalar backoff ile yönetilir.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger

from marketpulse.core.errors import MarketPulseError
from marketpulse.core.time import from_epoch_ms, to_epoch_ms
from marketpulse.core.types import Interval
from marketpulse.engine.ratelimit import RateLimiter, WeightLimit
from marketpulse.storage.models import Candle

KLINES_PATH = "/api/v3/klines"
EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"
TIME_PATH = "/api/v3/time"
TICKER_24H_PATH = "/api/v3/ticker/24hr"

MAX_KLINES_LIMIT = 1000
DEFAULT_TIMEOUT_SEC = 20.0
MAX_ATTEMPTS = 4
IP_BAN_DEFAULT_SEC = 120.0

# Endpoint ağırlıkları (Binance dokümanı). Bilinmeyen endpoint için 1 varsayılır.
ENDPOINT_WEIGHT: dict[str, int] = {
    KLINES_PATH: 2,
    EXCHANGE_INFO_PATH: 20,
    TIME_PATH: 1,
    TICKER_24H_PATH: 2,
}


class BinanceError(MarketPulseError):
    """Binance isteği kalıcı olarak başarısız (4xx ya da tükenen deneme hakkı)."""


class BinanceClient:
    """Tek bir Binance tabanı (spot veya futures) için REST istemcisi."""

    def __init__(
        self,
        base_url: str,
        limiter: RateLimiter,
        *,
        http: httpx.AsyncClient | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        backoff_base_sec: float = 0.5,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._limiter = limiter
        self._http = http or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SEC)
        self._owns_http = http is None
        self._max_attempts = max_attempts
        self._backoff_base_sec = backoff_base_sec
        self._sleep = sleep

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Ağırlık ayrılmış, yeniden denemeli GET. Kalıcı hatada `BinanceError` fırlatır."""
        weight = ENDPOINT_WEIGHT.get(path, 1)
        last_error: str = ""
        for attempt in range(1, self._max_attempts + 1):
            await self._limiter.acquire(weight)
            try:
                response = await self._http.get(f"{self._base_url}{path}", params=params)
            except httpx.HTTPError as exc:
                last_error = f"bağlantı hatası: {exc!r}"
                await self._backoff(attempt)
                continue
            self._sync_used_weight(response)
            if response.status_code == httpx.codes.OK:
                return response.json()
            last_error = self._handle_error_status(response, path)
            if response.status_code in (429, 418) or response.status_code >= 500:
                await self._backoff(attempt)
                continue
            raise BinanceError(f"{path} → HTTP {response.status_code}: {response.text[:200]}")
        raise BinanceError(f"{path} {self._max_attempts} denemede başarısız: {last_error}")

    async def server_time(self) -> datetime:
        payload = await self.get(TIME_PATH)
        return from_epoch_ms(int(payload["serverTime"]))

    async def weight_limit(self) -> WeightLimit | None:
        """exchangeInfo'daki REQUEST_WEIGHT limiti; bulunamazsa None."""
        payload = await self.get(EXCHANGE_INFO_PATH)
        for rule in payload.get("rateLimits", []):
            if rule.get("rateLimitType") != "REQUEST_WEIGHT":
                continue
            seconds = _interval_seconds(rule.get("interval", "MINUTE")) * int(
                rule.get("intervalNum", 1)
            )
            return WeightLimit(limit=int(rule["limit"]), window=timedelta(seconds=seconds))
        return None

    async def symbols(self) -> set[str]:
        """exchangeInfo'daki işlem gören sembol adları (sembol doğrulaması için)."""
        payload = await self.get(EXCHANGE_INFO_PATH)
        return {
            str(s["symbol"])
            for s in payload.get("symbols", [])
            if s.get("status", "TRADING") == "TRADING"
        }

    async def ticker_24h(self, symbol: str) -> dict[str, float]:
        payload = await self.get(TICKER_24H_PATH, {"symbol": symbol})
        return {
            "last_price": float(payload["lastPrice"]),
            "open_price": float(payload["openPrice"]),
            "change_pct": float(payload["priceChangePercent"]) / 100.0,
            "volume": float(payload["volume"]),
        }

    async def klines(
        self,
        symbol: str,
        interval: Interval,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = MAX_KLINES_LIMIT,
    ) -> list[Candle]:
        """Kapanmış mumlar. Oluşmakta olan son mum ayıklanır (look-ahead koruması).

        Binance `closeTime` alanını `openTime + interval - 1ms` verir; biz `openTime + interval`
        olarak normalize ederiz (ARCHITECTURE.md §6.1).
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval.value,
            "limit": min(limit, MAX_KLINES_LIMIT),
        }
        if start is not None:
            params["startTime"] = to_epoch_ms(start)
        if end is not None:
            params["endTime"] = to_epoch_ms(end)
        rows = await self.get(KLINES_PATH, params)
        return [_parse_kline(symbol, interval, row) for row in rows]

    def _sync_used_weight(self, response: httpx.Response) -> None:
        for header in ("x-mbx-used-weight-1m", "x-mbx-used-weight"):
            raw = response.headers.get(header)
            if raw is not None and raw.isdigit():
                self._limiter.observe_used_weight(int(raw))
                return

    def _handle_error_status(self, response: httpx.Response, path: str) -> str:
        if response.status_code == 429:
            retry_after = float(response.headers.get("retry-after", "5"))
            self._limiter.block_for(retry_after)
            return f"429 rate limit, {retry_after:.0f} sn"
        if response.status_code == 418:
            retry_after = float(response.headers.get("retry-after", IP_BAN_DEFAULT_SEC))
            self._limiter.block_for(retry_after)
            logger.warning("Binance IP ban (418): {s:.0f} sn REST durdu", s=retry_after)
            return f"418 IP ban, {retry_after:.0f} sn"
        return f"HTTP {response.status_code} ({path})"

    async def _backoff(self, attempt: int) -> None:
        await self._sleep(self._backoff_base_sec * (2 ** (attempt - 1)))


def _interval_seconds(interval: str) -> int:
    return {"SECOND": 1, "MINUTE": 60, "HOUR": 3600, "DAY": 86400}.get(interval.upper(), 60)


def _parse_kline(symbol: str, interval: Interval, row: list[Any]) -> Candle:
    open_time = from_epoch_ms(int(row[0]))
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time=open_time + interval.length,
        quote_volume=float(row[7]),
        trades=int(row[8]),
        taker_buy_base=float(row[9]),
    )
