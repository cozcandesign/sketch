"""Order flow toplayıcısı: WS mesajlarını dakikalık kovalara indirger (ARCHITECTURE.md §4).

**Saf sınıf**: ağ ve DB erişimi yoktur, saati dışarıdan alır. Böylece kova mantığı sahte mesajlarla
test edilebilir. Bağlantıyı ve yazmayı `orderflow_ws.py` yapar.

`coverage_seconds` neden var: bir dakikanın verisi eksikse (bağlantı kopuk kaldıysa) o dakikanın
hacmi olduğundan küçük görünür. Kapsama saniyesi bunu görünür kılar; order flow modülü düşük
kapsamalı dakikalarda güvenini düşürür, veriyi "tam" saymaz.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from marketpulse.core.time import floor_to_minute
from marketpulse.storage.models import Liquidation, OrderflowRow

MINUTE: Final = timedelta(minutes=1)
BPS: Final = 10_000.0


@dataclass
class _Bucket:
    """Tek sembol-dakika için biriken değerler."""

    symbol: str
    minute: datetime
    buy_vol: float = 0.0
    sell_vol: float = 0.0
    trade_count: int = 0
    liq_long_usd: float = 0.0
    liq_short_usd: float = 0.0
    liq_count: int = 0
    bid_qty_sum: float = 0.0
    ask_qty_sum: float = 0.0
    spread_bps_sum: float = 0.0
    book_samples: int = 0
    coverage_seconds: float = 0.0

    def to_row(self) -> OrderflowRow:
        samples = self.book_samples
        return OrderflowRow(
            symbol=self.symbol,
            ts=self.minute,
            buy_vol=self.buy_vol,
            sell_vol=self.sell_vol,
            cvd_delta=self.buy_vol - self.sell_vol,
            trade_count=self.trade_count,
            liq_long_usd=self.liq_long_usd,
            liq_short_usd=self.liq_short_usd,
            liq_count=self.liq_count,
            top20_bid_qty=self.bid_qty_sum / samples if samples else None,
            top20_ask_qty=self.ask_qty_sum / samples if samples else None,
            top20_imbalance=_imbalance(self.bid_qty_sum, self.ask_qty_sum) if samples else None,
            spread_bps=self.spread_bps_sum / samples if samples else None,
            coverage_seconds=round(self.coverage_seconds, 3),
        )


@dataclass
class OrderflowAggregator:
    """Dakika kovaları + bağlantı kapsaması. Kapanan dakikaları `take_closed` ile verir."""

    _buckets: dict[tuple[str, datetime], _Bucket] = field(default_factory=dict)
    _connected_since: datetime | None = None

    def mark_connected(self, ts: datetime) -> None:
        if self._connected_since is None:
            self._connected_since = ts

    def mark_disconnected(self, ts: datetime) -> None:
        """Kopmada o ana kadarki kapsama süresi kovalara yazılır; sonrası sayılmaz."""
        if self._connected_since is None:
            return
        for bucket in self._buckets.values():
            bucket.coverage_seconds += _overlap_seconds(
                bucket.minute, bucket.minute + MINUTE, self._connected_since, ts
            )
        self._connected_since = None

    def add_trade(self, symbol: str, ts: datetime, *, qty: float, is_buyer_maker: bool) -> None:
        """aggTrade. `is_buyer_maker=True` → saldırgan taraf satıcıdır (satış hacmi)."""
        bucket = self._bucket(symbol, ts)
        if is_buyer_maker:
            bucket.sell_vol += qty
        else:
            bucket.buy_vol += qty
        bucket.trade_count += 1

    def add_liquidation(self, liquidation: Liquidation) -> None:
        bucket = self._bucket(liquidation.symbol, liquidation.ts)
        if liquidation.side == "long":
            bucket.liq_long_usd += liquidation.usd
        else:
            bucket.liq_short_usd += liquidation.usd
        bucket.liq_count += 1

    def add_book(
        self,
        symbol: str,
        ts: datetime,
        *,
        bids: Sequence[tuple[float, float]],
        asks: Sequence[tuple[float, float]],
    ) -> None:
        """Top-20 anlık görüntüsü. Dakika içindeki örneklerin ortalaması saklanır."""
        if not bids or not asks:
            return
        bucket = self._bucket(symbol, ts)
        bucket.bid_qty_sum += sum(qty for _, qty in bids)
        bucket.ask_qty_sum += sum(qty for _, qty in asks)
        best_bid, best_ask = bids[0][0], asks[0][0]
        mid = (best_bid + best_ask) / 2.0
        if mid > 0:
            bucket.spread_bps_sum += (best_ask - best_bid) / mid * BPS
        bucket.book_samples += 1

    def take_closed(self, now: datetime) -> list[OrderflowRow]:
        """Kapanmış dakikaların satırları. Açık dakika asla verilmez (yarım veri yazılmaz)."""
        closed = [key for key, bucket in self._buckets.items() if bucket.minute + MINUTE <= now]
        rows: list[OrderflowRow] = []
        for key in sorted(closed, key=lambda item: (item[1], item[0])):
            bucket = self._buckets.pop(key)
            if self._connected_since is not None:
                bucket.coverage_seconds += _overlap_seconds(
                    bucket.minute, bucket.minute + MINUTE, self._connected_since, now
                )
            rows.append(bucket.to_row())
        return rows

    def open_minutes(self) -> int:
        return len(self._buckets)

    def _bucket(self, symbol: str, ts: datetime) -> _Bucket:
        minute = floor_to_minute(ts)
        key = (symbol, minute)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(symbol=symbol, minute=minute)
            self._buckets[key] = bucket
        return bucket


def _imbalance(bid: float, ask: float) -> float | None:
    """(bid − ask) / (bid + ask): +1 tamamen alış tarafı, −1 tamamen satış tarafı."""
    total = bid + ask
    if total <= 0:
        return None
    return (bid - ask) / total


def _overlap_seconds(
    start: datetime, end: datetime, other_start: datetime, other_end: datetime
) -> float:
    """İki zaman aralığının kesişimi (saniye); kesişmiyorsa 0."""
    latest_start = max(start, other_start)
    earliest_end = min(end, other_end)
    return max(0.0, (earliest_end - latest_start).total_seconds())
