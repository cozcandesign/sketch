"""Point-in-time FeatureStore (ARCHITECTURE.md §7, CLAUDE.md §9).

Sinyal modülleri ham DB'ye **erişmez**; yalnızca burada üretilen `FeatureSnapshot`'ı görür. Snapshot
`as_of` anında gerçekten bilinebilecek veriden oluşur:

- yalnızca **kapanmış** mumlar (`close_time <= as_of`); oluşmakta olan mum asla dahil değil,
- her zaman serisi geriye bakış penceresiyle sınırlı,
- kapsama (`coverage`) ve tazelik (`freshness`) ölçülür; eksik veri gizlenmez, modüle bildirilir.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

import pandas as pd

from marketpulse.core.types import Interval
from marketpulse.features.snapshot import (
    FeatureSnapshot,
    coverage_key,
    coverage_ratio,
    empty_frame,
    freshness_ratio,
    last_price,
)
from marketpulse.storage.models import Candle
from marketpulse.storage.repository import Repository

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
            coverage[coverage_key(interval)] = coverage_ratio(len(frame), interval, window)
            freshness[coverage_key(interval)] = freshness_ratio(frame, interval, moment)
        return FeatureSnapshot(
            symbol=symbol,
            as_of=moment,
            candles=candles,
            coverage=coverage,
            freshness=freshness,
            price=last_price(candles),
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


def _require_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        msg = "as_of timezone-aware olmalı (UTC); naive datetime kabul edilmez"
        raise ValueError(msg)
    return moment.astimezone(UTC)
