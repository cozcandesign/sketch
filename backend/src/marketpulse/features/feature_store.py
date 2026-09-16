"""Point-in-time FeatureStore (ARCHITECTURE.md §7, CLAUDE.md §9).

Sinyal modülleri ham DB'ye **erişmez**; yalnızca burada üretilen `FeatureSnapshot`'ı görür. Snapshot
`as_of` anında gerçekten bilinebilecek veriden oluşur:

- yalnızca **kapanmış** mumlar (`close_time <= as_of`); oluşmakta olan mum asla dahil değil,
- her zaman serisi geriye bakış penceresiyle sınırlı,
- kapsama (`coverage`) ve tazelik (`freshness`) ölçülür; eksik veri gizlenmez, modüle bildirilir.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

import pandas as pd
from pydantic import BaseModel

from marketpulse.core.types import Interval
from marketpulse.features.snapshot import (
    DATASET_NAMES,
    FeatureSnapshot,
    coverage_for,
    coverage_key,
    coverage_ratio,
    dataset_frame,
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

# Türev veri setlerinin geriye bakış pencereleri (ARCHITECTURE.md §7). Order flow penceresi kısa:
# 48 saatten eski dakika özetleri sinyal için değer taşımıyor, sorguyu ise ağırlaştırıyor.
DATASET_LOOKBACK: Final[Mapping[str, timedelta]] = {
    "funding": timedelta(days=60),
    "funding_live": timedelta(days=2),
    "open_interest": timedelta(days=30),
    "long_short": timedelta(days=30),
    "taker_volume": timedelta(days=30),
    "orderflow_1m": timedelta(hours=48),
    "liquidations": timedelta(hours=24),
}
# Kapsama için "beklenen satır" hesabı: veri setinin doğal örnekleme aralığı.
DATASET_INTERVAL: Final[Mapping[str, timedelta]] = {
    "funding": timedelta(hours=8),
    "funding_live": timedelta(minutes=1),
    "open_interest": timedelta(minutes=5),
    "long_short": timedelta(minutes=5),
    "taker_volume": timedelta(minutes=5),
    "orderflow_1m": timedelta(minutes=1),
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
        datasets = await self._load_datasets(symbol, moment, coverage, freshness)
        return FeatureSnapshot(
            symbol=symbol,
            as_of=moment,
            candles=candles,
            coverage=coverage,
            freshness=freshness,
            price=last_price(candles),
            datasets=datasets,
        )

    async def _load_datasets(
        self,
        symbol: str,
        as_of: datetime,
        coverage: dict[str, float],
        freshness: dict[str, float],
    ) -> dict[str, pd.DataFrame]:
        """Türev veri setleri; her biri kendi penceresiyle ve `ts <= as_of` kesmesiyle."""
        datasets: dict[str, pd.DataFrame] = {}
        for name in DATASET_NAMES:
            window = DATASET_LOOKBACK[name]
            rows = await self._read_dataset(name, symbol, as_of, as_of - window)
            frame = dataset_frame(name, rows)
            datasets[name] = frame
            interval = DATASET_INTERVAL.get(name)
            coverage[name] = (
                coverage_for(len(frame), interval, window)
                if interval is not None
                # Likidasyonlar olay akışıdır: "beklenen satır" diye bir şey yok, ya var ya yok.
                else (1.0 if not frame.empty else 0.0)
            )
            freshness[name] = _dataset_freshness(frame, interval, as_of)
        return datasets

    async def _read_dataset(
        self, name: str, symbol: str, as_of: datetime, start: datetime
    ) -> list[dict[str, object]]:
        readers: dict[str, _DatasetReader] = {
            "funding": self._repo.get_funding_rates,
            "funding_live": self._repo.get_funding_live,
            "open_interest": self._repo.get_open_interest,
            "long_short": self._repo.get_long_short,
            "taker_volume": self._repo.get_taker_volume,
            "orderflow_1m": self._repo.get_orderflow,
            "liquidations": self._repo.get_liquidations,
        }
        rows = await readers[name](symbol, as_of=as_of, start=start)
        return [_as_row(item) for item in rows]


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


class _DatasetReader(Protocol):
    """Türev veri seti okuyucusu: `(symbol, as_of, start)` → model listesi."""

    async def __call__(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> Sequence[BaseModel]: ...


def _as_row(item: BaseModel) -> dict[str, object]:
    """Pydantic modelini sözlüğe çevirir; `funding_time` alanı `ts` olarak normalize edilir."""
    data = dict(item.model_dump())
    if "ts" not in data and "funding_time" in data:
        data["ts"] = data.pop("funding_time")
    return data


def _dataset_freshness(frame: pd.DataFrame, interval: timedelta | None, as_of: datetime) -> float:
    """Son satırın yaşı / beklenen aralık. Aralık bilinmiyorsa yalnızca boşluk kontrolü."""
    if frame.empty:
        return float("inf")
    last = pd.Timestamp(frame.index[-1]).to_pydatetime()
    age = (as_of - last).total_seconds()
    if interval is None:
        return 0.0
    return max(0.0, age / interval.total_seconds())


def _require_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        msg = "as_of timezone-aware olmalı (UTC); naive datetime kabul edilmez"
        raise ValueError(msg)
    return moment.astimezone(UTC)
