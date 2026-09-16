"""`FeatureSnapshot`: `as_of` anında dondurulmuş veri görüntüsü — **saf veri yapısı**.

Yükleyici (`feature_store.py`) DB'ye bağlanır; burada hiçbir I/O yoktur. Ayrım bilinçlidir: sinyal
modülleri yalnızca bu dosyaya bağlanır, böylece "sinyaller storage'a erişemez" kuralı import
zincirinde de doğrulanabilir (import-linter sözleşmesi).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

import pandas as pd

from marketpulse.core.types import Interval

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
PRICE_INTERVAL: Final = Interval.M1  # K16: fiyat referansı spot 1 dk kapanışı

# Türev veri setlerinin sütunları (ARCHITECTURE.md §6.1). Boş çerçeve de bu sütunlarla üretilir ki
# modüller `df.empty` dışında hiçbir özel durum bilmek zorunda kalmasın.
DATASET_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = {
    "funding": ("rate", "mark_price"),
    "funding_live": ("last_rate", "next_funding_time", "mark_price", "index_price"),
    "open_interest": ("oi", "oi_value_usd", "source"),
    "long_short": ("kind", "long_ratio", "short_ratio", "ratio"),
    "taker_volume": ("buy_vol", "sell_vol", "ratio"),
    "orderflow_1m": (
        "buy_vol",
        "sell_vol",
        "cvd_delta",
        "trade_count",
        "liq_long_usd",
        "liq_short_usd",
        "liq_count",
        "top20_bid_qty",
        "top20_ask_qty",
        "top20_imbalance",
        "depth1pct_bid_usd",
        "depth1pct_ask_usd",
        "depth1pct_imbalance",
        "spread_bps",
        "coverage_seconds",
    ),
    "liquidations": ("side", "qty", "price", "usd"),
}
DATASET_NAMES: Final[tuple[str, ...]] = tuple(DATASET_COLUMNS)


@dataclass(frozen=True)
class FeatureSnapshot:
    """`as_of` anındaki dondurulmuş veri görüntüsü.

    Snapshot faz faz büyür: Faz 2'de mumlar; order flow Faz 3'te, haber Faz 4'te, makro ve
    sentiment Faz 5'te eklenir. Var olmayan veri için uydurma alan tutulmaz (CLAUDE.md §14.2).
    """

    symbol: str
    as_of: datetime
    candles: Mapping[Interval, pd.DataFrame]
    coverage: Mapping[str, float]
    freshness: Mapping[str, float]
    price: float | None
    # Türev veri setleri (Faz 3). Yoksa boş çerçeve gelir; modül "veri yok" der.
    datasets: Mapping[str, pd.DataFrame] = field(default_factory=dict)

    def dataset(self, name: str) -> pd.DataFrame:
        """Adlandırılmış türev veri seti; yoksa doğru sütunlu boş çerçeve."""
        frame = self.datasets.get(name)
        return frame if frame is not None else dataset_frame(name)

    def has(self, name: str) -> bool:
        return not self.dataset(name).empty

    def frame(self, interval: Interval) -> pd.DataFrame:
        """İstenen zaman diliminin mumları; yoksa boş çerçeve (KeyError değil)."""
        return self.candles.get(interval, empty_frame())

    def bars(self, interval: Interval) -> int:
        return len(self.frame(interval))

    def coverage_of(self, interval: Interval) -> float:
        return self.coverage.get(coverage_key(interval), 0.0)

    def freshness_of(self, interval: Interval) -> float:
        return self.freshness.get(coverage_key(interval), float("inf"))

    def is_stale(self, interval: Interval) -> bool:
        """Son mum, bir tam periyottan fazla gecikmişse veri bayattır."""
        return self.freshness_of(interval) > 1.0


def empty_frame() -> pd.DataFrame:
    """Sütunları doğru, satırı olmayan çerçeve — modüller `df.empty` ile "veri yok" der."""
    return pd.DataFrame(
        {name: pd.Series(dtype="float64") for name in FRAME_COLUMNS},
        index=pd.DatetimeIndex([], name="close_time"),
    )


def dataset_frame(name: str, rows: list[dict[str, object]] | None = None) -> pd.DataFrame:
    """`ts` indeksli veri seti çerçevesi. Satır yoksa sütunlar yine doğru olur."""
    columns = DATASET_COLUMNS.get(name, ())
    if not rows:
        return pd.DataFrame(
            {column: pd.Series(dtype="object") for column in columns},
            index=pd.DatetimeIndex([], name="ts"),
        )
    frame = pd.DataFrame(rows, index=pd.DatetimeIndex([row["ts"] for row in rows], name="ts"))
    frame = frame.drop(columns=["ts", "symbol"], errors="ignore").sort_index()
    # Eksik sütunlar NaN olarak eklenir: modüller sütunun varlığını değil, değerin olup olmadığını
    # kontrol etsin. (Veri kaynağı bir alanı hiç yazmamış olabilir.)
    missing = [column for column in columns if column not in frame.columns]
    for column in missing:
        frame[column] = pd.Series(dtype="float64")
    return frame


def coverage_key(interval: Interval) -> str:
    return f"candles_{interval.value}"


def coverage_ratio(rows: int, interval: Interval, window: timedelta) -> float:
    """Kapsama = mevcut satır / pencereye sığan satır (0..1)."""
    return coverage_for(rows, interval.length, window)


def coverage_for(rows: int, sampling: timedelta, window: timedelta) -> float:
    """Aynı hesap, örnekleme aralığı doğrudan verildiğinde (türev veri setleri)."""
    expected = window / sampling
    if expected <= 0:
        return 0.0
    return min(1.0, rows / expected)


def freshness_ratio(frame: pd.DataFrame, interval: Interval, as_of: datetime) -> float:
    """Tazelik = (as_of − son mum kapanışı) / periyot. 0 = az önce kapandı, >1 = bayat."""
    if frame.empty:
        return float("inf")
    last_close = pd.Timestamp(frame.index[-1]).to_pydatetime()
    age_sec = (as_of - last_close).total_seconds()
    return max(0.0, age_sec / interval.length.total_seconds())


def last_price(candles: Mapping[Interval, pd.DataFrame]) -> float | None:
    """Fiyat referansı: 1 dk kapanışı; yoksa elde olan en ince zaman diliminin kapanışı."""
    for interval in (PRICE_INTERVAL, *Interval):
        frame = candles.get(interval)
        if frame is not None and not frame.empty:
            return float(frame["close"].iloc[-1])
    return None
