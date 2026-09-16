"""Point-in-time FeatureStore (ARCHITECTURE.md §7, CLAUDE.md §9).

Sinyal modülleri ham DB'ye **erişmez**; yalnızca burada üretilen `FeatureSnapshot`'ı görür. Snapshot
`as_of` anında gerçekten bilinebilecek veriden oluşur:

- yalnızca **kapanmış** mumlar (`close_time <= as_of`); oluşmakta olan mum asla dahil değil,
- her zaman serisi geriye bakış penceresiyle sınırlı,
- kapsama (`coverage`) ve tazelik (`freshness`) ölçülür; eksik veri gizlenmez, modüle bildirilir.

Snapshot faz faz büyür: Faz 2'de mumlar; order flow Faz 3'te, haber Faz 4'te, makro ve sentiment
Faz 5'te eklenir. Var olmayan veri için uydurma alan tutulmaz (CLAUDE.md §14.2).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import pandas as pd

from marketpulse.core.types import Interval
from marketpulse.storage.models import Candle
from marketpulse.storage.repository import Repository

FRAME_COLUMNS: Final = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trades",
    "taker_buy_base",
)

# Geriye bakış pencereleri (ARCHITECTURE.md §7). Uzun pencere = daha iyi yüzdelik ve profil,
# daha yavaş sorgu; bu değerler ölçülen ihtiyaca göre seçildi.
DEFAULT_LOOKBACK: Final[Mapping[Interval, timedelta]] = {
    Interval.M1: timedelta(days=2),
    Interval.M5: timedelta(days=7),
    Interval.M15: timedelta(days=30),
    Interval.H1: timedelta(days=90),
    Interval.H4: timedelta(days=365),
    Interval.D1: timedelta(days=730),
}
PRICE_INTERVAL: Final = Interval.M1  # K16: fiyat referansı spot 1 dk kapanışı


@dataclass(frozen=True)
class FeatureSnapshot:
    """`as_of` anındaki dondurulmuş veri görüntüsü."""

    symbol: str
    as_of: datetime
    candles: Mapping[Interval, pd.DataFrame]
    coverage: Mapping[str, float]
    freshness: Mapping[str, float]
    price: float | None

    def frame(self, interval: Interval) -> pd.DataFrame:
        """İstenen zaman diliminin mumları; yoksa boş çerçeve (KeyError değil)."""
        return self.candles.get(interval, empty_frame())

    def bars(self, interval: Interval) -> int:
        return len(self.frame(interval))

    def coverage_of(self, interval: Interval) -> float:
        return self.coverage.get(_key(interval), 0.0)

    def is_stale(self, interval: Interval) -> bool:
        """Son mum, bir tam periyottan fazla gecikmişse veri bayattır."""
        return self.freshness.get(_key(interval), 1.0) > 1.0


class FeatureStore:
    """Repository üzerinden point-in-time snapshot üretir."""

    def __init__(
        self,
        repo: Repository,
        *,
        lookback: Mapping[Interval, timedelta] | None = None,
    ) -> None:
        self._repo = repo
        self._lookback = dict(lookback or DEFAULT_LOOKBACK)

    async def snapshot(
        self, symbol: str, as_of: datetime, *, intervals: Sequence[Interval] | None = None
    ) -> FeatureSnapshot:
        """`as_of` anındaki snapshot. `as_of` timezone-aware UTC olmalıdır."""
        moment = _require_utc(as_of)
        wanted = tuple(intervals) if intervals is not None else tuple(Interval)
        candles: dict[Interval, pd.DataFrame] = {}
        coverage: dict[str, float] = {}
        freshness: dict[str, float] = {}
        for interval in wanted:
            window = self._lookback.get(interval, DEFAULT_LOOKBACK[interval])
            rows = await self._repo.get_candles(
                symbol, interval, as_of=moment, start=moment - window
            )
            frame = candles_to_frame(rows)
            candles[interval] = frame
            coverage[_key(interval)] = _coverage(len(frame), interval, window)
            freshness[_key(interval)] = _freshness(frame, interval, moment)
        return FeatureSnapshot(
            symbol=symbol,
            as_of=moment,
            candles=candles,
            coverage=coverage,
            freshness=freshness,
            price=_last_price(candles),
        )


def candles_to_frame(candles: Sequence[Candle]) -> pd.DataFrame:
    """Mum listesini `close_time` indeksli çerçeveye çevirir.

    İndeks `close_time`'dır: bilgi o anda kullanılabilir hale gelir. `open_time` sütun olarak kalır.
    """
    if not candles:
        return empty_frame()
    frame = pd.DataFrame(
        {
            "open_time": [c.open_time for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
            "quote_volume": [c.quote_volume for c in candles],
            "trades": [c.trades for c in candles],
            "taker_buy_base": [c.taker_buy_base for c in candles],
        },
        index=pd.DatetimeIndex([c.close_time for c in candles], name="close_time"),
    )
    return frame.sort_index()


def empty_frame() -> pd.DataFrame:
    """Sütunları doğru, satırı olmayan çerçeve — modüller `df.empty` ile "veri yok" der."""
    return pd.DataFrame(
        {name: pd.Series(dtype="float64") for name in FRAME_COLUMNS},
        index=pd.DatetimeIndex([], name="close_time"),
    )


def _coverage(rows: int, interval: Interval, window: timedelta) -> float:
    """Kapsama = mevcut satır / pencereye sığan satır (0..1)."""
    expected = window / interval.length
    if expected <= 0:
        return 0.0
    return min(1.0, rows / expected)


def _freshness(frame: pd.DataFrame, interval: Interval, as_of: datetime) -> float:
    """Tazelik = (as_of − son mum kapanışı) / periyot. 0 = az önce kapandı, >1 = bayat."""
    if frame.empty:
        return float("inf")
    last_close = pd.Timestamp(frame.index[-1]).to_pydatetime()
    age_sec = (as_of - last_close).total_seconds()
    return max(0.0, age_sec / interval.length.total_seconds())


def _last_price(candles: Mapping[Interval, pd.DataFrame]) -> float | None:
    """Fiyat referansı: 1 dk kapanışı; yoksa elde olan en ince zaman diliminin kapanışı."""
    for interval in (PRICE_INTERVAL, *Interval):
        frame = candles.get(interval)
        if frame is not None and not frame.empty:
            return float(frame["close"].iloc[-1])
    return None


def _key(interval: Interval) -> str:
    return f"candles_{interval.value}"


def _require_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        msg = "as_of timezone-aware olmalı (UTC); naive datetime kabul edilmez"
        raise ValueError(msg)
    return moment.astimezone(UTC)
