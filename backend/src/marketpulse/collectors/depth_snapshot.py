"""±%1 order book derinliği (ARCHITECTURE.md §4).

Top-20 dengesizliğini WS akışı verir; bu collector fiyatın **±%1 çevresindeki** toplam derinliği
REST anlık görüntüsünden hesaplar. İki ölçü farklı şeyleri söyler: top-20 anlık baskıyı, ±%1 ise
gerçekten emilebilecek büyüklüğü.

Ham derinlik saklanmaz (K21): yalnızca iki USD toplamı ve dengesizlik `orderflow_1m` satırının
`depth1pct_*` sütunlarına yazılır.

`spread_bps` bu collector tarafından **yazılmaz**: aynı sütuna WS akışı da yazıyor ve o saniyede
10 örnek alıyor. 30 saniyede bir alınan tek örnekle üzerine yazmak daha kötü bir ölçüm olurdu.
Özet yine de spread'i hesaplar; hata ayıklama ve API için kullanılabilir.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from marketpulse.collectors.binance_futures import DepthSnapshot, FuturesClient
from marketpulse.core.clock import Clock
from marketpulse.core.time import floor_to_minute
from marketpulse.storage.models import OrderflowRow
from marketpulse.storage.repository import Repository

COLLECTOR_NAME: Final = "depth_snapshot"
DEPTH_BAND: Final = 0.01  # ±%1
BPS: Final = 10_000.0


@dataclass(frozen=True)
class DepthSummary:
    """Anlık görüntüden çıkarılan özet. Fiyat yoksa `None` alanlar kalır."""

    bid_usd: float
    ask_usd: float
    imbalance: float | None
    spread_bps: float | None


def summarize(snapshot: DepthSnapshot, *, band: float = DEPTH_BAND) -> DepthSummary | None:
    """Orta fiyatın ±`band` aralığındaki toplam USD derinliği ve spread."""
    mid = snapshot.mid_price
    if mid is None or mid <= 0:
        return None
    low, high = mid * (1 - band), mid * (1 + band)
    bid_usd = sum(price * qty for price, qty in snapshot.bids if price >= low)
    ask_usd = sum(price * qty for price, qty in snapshot.asks if price <= high)
    total = bid_usd + ask_usd
    best_bid, best_ask = snapshot.bids[0][0], snapshot.asks[0][0]
    return DepthSummary(
        bid_usd=bid_usd,
        ask_usd=ask_usd,
        imbalance=(bid_usd - ask_usd) / total if total > 0 else None,
        spread_bps=(best_ask - best_bid) / mid * BPS,
    )


class DepthSnapshotCollector:
    """Her çağrıda semboller için anlık görüntü alır ve o dakikanın satırına yazar."""

    name = COLLECTOR_NAME

    def __init__(
        self, client: FuturesClient, repo: Repository, clock: Clock, *, symbols: Sequence[str]
    ) -> None:
        self._client = client
        self._repo = repo
        self._clock = clock
        self._symbols = list(symbols)

    async def poll(self) -> int:
        """Yazılan satır sayısı. Aynı dakikaya ikinci yazım son görüntüyle günceller."""
        minute = floor_to_minute(self._clock.now())
        rows: list[OrderflowRow] = []
        for symbol in self._symbols:
            snapshot = await self._client.depth(symbol)
            summary = summarize(snapshot)
            if summary is None:
                continue
            rows.append(
                OrderflowRow(
                    symbol=symbol,
                    ts=minute,
                    depth1pct_bid_usd=summary.bid_usd,
                    depth1pct_ask_usd=summary.ask_usd,
                    depth1pct_imbalance=summary.imbalance,
                )
            )
        if not rows:
            return 0
        return await self._repo.upsert_orderflow(rows)
