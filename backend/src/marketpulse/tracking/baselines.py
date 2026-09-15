"""Referans tahminciler (ARCHITECTURE.md §11.4).

Bunlar sinyal değildir; **yenilmesi gereken taban çizgisidir**. Gerçek modüller bu ikisini
geçemiyorsa işe yaramıyor demektir.

- `climatology`: son 90 günde ufuk uzunluğundaki hareketlerin yukarı çıkma oranı.
- `momentum`: son kapanmış bağlam mumu yeşilse %60, kırmızıysa %40.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from marketpulse.core.types import Horizon
from marketpulse.storage.repository import Repository

CLIMATOLOGY_LOOKBACK = timedelta(days=90)
MIN_CLIMATOLOGY_SAMPLES = 30
MOMENTUM_UP = 0.6
MOMENTUM_DOWN = 0.4
NEUTRAL = 0.5

CLIMATOLOGY_VERSION = "baseline-climatology-1"
MOMENTUM_VERSION = "baseline-momentum-1"


@dataclass(frozen=True)
class BaselineResult:
    """Tek bir referans tahminin çıktısı."""

    version: str
    p_up: float
    samples: int
    note_tr: str


async def climatology(
    repo: Repository, symbol: str, horizon: Horizon, as_of: datetime
) -> BaselineResult:
    """Taban oranı: geçmişte bu ufukta fiyat ne sıklıkla yukarı kapanmış?

    Ufuk uzunluğu, ufkun ana zaman diliminin tam katıdır; kayan pencerelerle örnek sayısı artırılır.
    Yeterli örnek yoksa %50 döner ve bunu notta söyler.
    """
    interval = horizon.base_interval
    step = int(horizon.length / interval.length)
    candles = await repo.get_candles(
        symbol, interval, as_of=as_of, start=as_of - CLIMATOLOGY_LOOKBACK
    )
    closes = [c.close for c in candles]
    if len(closes) <= step:
        return BaselineResult(
            CLIMATOLOGY_VERSION, NEUTRAL, 0, "yeterli geçmiş yok, %50 kabul edildi"
        )
    ups = sum(1 for i in range(len(closes) - step) if closes[i + step] > closes[i])
    samples = len(closes) - step
    if samples < MIN_CLIMATOLOGY_SAMPLES:
        return BaselineResult(
            CLIMATOLOGY_VERSION, NEUTRAL, samples, f"örnek az ({samples}), %50 kabul edildi"
        )
    return BaselineResult(
        CLIMATOLOGY_VERSION,
        ups / samples,
        samples,
        f"son {CLIMATOLOGY_LOOKBACK.days} günde {samples} pencerenin {ups} tanesi yukarı kapandı",
    )


async def momentum(
    repo: Repository, symbol: str, horizon: Horizon, as_of: datetime
) -> BaselineResult:
    """Son kapanmış bağlam mumunun rengini devam ettirir."""
    interval = horizon.context_interval
    candle = await repo.latest_candle(symbol, interval, as_of=as_of)
    if candle is None:
        return BaselineResult(MOMENTUM_VERSION, NEUTRAL, 0, "bağlam mumu yok, %50 kabul edildi")
    direction = "yeşil" if candle.is_green else "kırmızı"
    return BaselineResult(
        MOMENTUM_VERSION,
        MOMENTUM_UP if candle.is_green else MOMENTUM_DOWN,
        1,
        f"son kapanmış {interval.value} mumu {direction}",
    )
