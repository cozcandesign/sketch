"""Binance USDT-M futures public REST uçları (ARCHITECTURE.md §4).

Yalnızca public endpoint; imzalı istek yoktur (CLAUDE.md §1). `BinanceClient` üzerine kurulur:
ağırlık limiti, backoff ve hata yönetimi orada.

**Şema notu:** alan adları Binance dokümanına göre yazılmıştır. Bu geliştirme ortamından
`fapi.binance.com` erişilemediği için canlı yanıtla karşılaştırma **kullanıcının makinesinde**
yapılacaktır; gerçek yanıt farklı çıkarsa ARCHITECTURE §4 tablosu ve buradaki ayrıştırıcılar aynı
commit'te güncellenir (CLAUDE.md §12.5).
"""

from datetime import datetime
from typing import Any, Final, Literal

from marketpulse.collectors.binance_client import BinanceClient
from marketpulse.core.time import from_epoch_ms, to_epoch_ms
from marketpulse.storage.models import (
    FundingLive,
    FundingRate,
    LongShortPoint,
    OpenInterestPoint,
    TakerVolumePoint,
)

FUNDING_RATE_PATH: Final = "/fapi/v1/fundingRate"
PREMIUM_INDEX_PATH: Final = "/fapi/v1/premiumIndex"
OPEN_INTEREST_PATH: Final = "/fapi/v1/openInterest"
OPEN_INTEREST_HIST_PATH: Final = "/futures/data/openInterestHist"
GLOBAL_LONG_SHORT_PATH: Final = "/futures/data/globalLongShortAccountRatio"
TOP_ACCOUNT_PATH: Final = "/futures/data/topLongShortAccountRatio"
TOP_POSITION_PATH: Final = "/futures/data/topLongShortPositionRatio"
TAKER_VOLUME_PATH: Final = "/futures/data/takerlongshortRatio"

# `/futures/data/*` uçları en fazla 500 satır ve yalnızca son 30 gün verir (K5).
MAX_DATA_LIMIT: Final = 500
MAX_FUNDING_LIMIT: Final = 1000
DEFAULT_PERIOD: Final = "5m"

LongShortKind = Literal["global_account", "top_account", "top_position"]
LONG_SHORT_KINDS: Final[tuple[LongShortKind, ...]] = (
    "global_account",
    "top_account",
    "top_position",
)
LONG_SHORT_PATHS: Final[dict[LongShortKind, str]] = {
    "global_account": GLOBAL_LONG_SHORT_PATH,
    "top_account": TOP_ACCOUNT_PATH,
    "top_position": TOP_POSITION_PATH,
}


class FuturesClient:
    """Türev metrikleri için ince sarmalayıcı; her metot tipli model listesi döner."""

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    async def funding_history(
        self, symbol: str, *, start: datetime | None = None, limit: int = MAX_FUNDING_LIMIT
    ) -> list[FundingRate]:
        params: dict[str, Any] = {"symbol": symbol, "limit": min(limit, MAX_FUNDING_LIMIT)}
        if start is not None:
            params["startTime"] = to_epoch_ms(start)
        rows = await self._client.get(FUNDING_RATE_PATH, params)
        return [
            FundingRate(
                symbol=symbol,
                funding_time=from_epoch_ms(int(row["fundingTime"])),
                rate=float(row["fundingRate"]),
                mark_price=_optional_float(row.get("markPrice")),
            )
            for row in rows
        ]

    async def funding_live(self, symbol: str, *, now: datetime) -> FundingLive:
        """Anlık funding göstergesi. `now` çağıranın saatidir (modüller saate erişmez)."""
        payload = await self._client.get(PREMIUM_INDEX_PATH, {"symbol": symbol})
        next_funding = payload.get("nextFundingTime")
        return FundingLive(
            symbol=symbol,
            ts=from_epoch_ms(int(payload["time"])) if payload.get("time") else now,
            last_rate=float(payload["lastFundingRate"]),
            next_funding_time=from_epoch_ms(int(next_funding)) if next_funding else None,
            mark_price=_optional_float(payload.get("markPrice")),
            index_price=_optional_float(payload.get("indexPrice")),
        )

    async def open_interest_live(self, symbol: str, *, now: datetime) -> OpenInterestPoint:
        payload = await self._client.get(OPEN_INTEREST_PATH, {"symbol": symbol})
        return OpenInterestPoint(
            symbol=symbol,
            ts=from_epoch_ms(int(payload["time"])) if payload.get("time") else now,
            oi=float(payload["openInterest"]),
            oi_value_usd=None,
            source="live",
        )

    async def open_interest_history(
        self, symbol: str, *, period: str = DEFAULT_PERIOD, limit: int = MAX_DATA_LIMIT
    ) -> list[OpenInterestPoint]:
        rows = await self._client.get(
            OPEN_INTEREST_HIST_PATH,
            {"symbol": symbol, "period": period, "limit": min(limit, MAX_DATA_LIMIT)},
        )
        return [
            OpenInterestPoint(
                symbol=symbol,
                ts=from_epoch_ms(int(row["timestamp"])),
                oi=float(row["sumOpenInterest"]),
                oi_value_usd=_optional_float(row.get("sumOpenInterestValue")),
                source="hist",
            )
            for row in rows
        ]

    async def long_short(
        self,
        symbol: str,
        kind: LongShortKind,
        *,
        period: str = DEFAULT_PERIOD,
        limit: int = MAX_DATA_LIMIT,
    ) -> list[LongShortPoint]:
        rows = await self._client.get(
            LONG_SHORT_PATHS[kind],
            {"symbol": symbol, "period": period, "limit": min(limit, MAX_DATA_LIMIT)},
        )
        return [
            LongShortPoint(
                symbol=symbol,
                ts=from_epoch_ms(int(row["timestamp"])),
                kind=kind,
                long_ratio=float(row["longAccount"]),
                short_ratio=float(row["shortAccount"]),
                ratio=float(row["longShortRatio"]),
            )
            for row in rows
        ]

    async def taker_volume(
        self, symbol: str, *, period: str = DEFAULT_PERIOD, limit: int = MAX_DATA_LIMIT
    ) -> list[TakerVolumePoint]:
        rows = await self._client.get(
            TAKER_VOLUME_PATH,
            {"symbol": symbol, "period": period, "limit": min(limit, MAX_DATA_LIMIT)},
        )
        return [
            TakerVolumePoint(
                symbol=symbol,
                ts=from_epoch_ms(int(row["timestamp"])),
                buy_vol=float(row["buyVol"]),
                sell_vol=float(row["sellVol"]),
                ratio=float(row["buySellRatio"]),
            )
            for row in rows
        ]


def _optional_float(value: Any) -> float | None:
    """Binance sayıları string olarak döner; alan yoksa None (0.0 değil — bu ikisi farklıdır)."""
    if value is None or value == "":
        return None
    return float(value)
