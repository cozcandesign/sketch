"""Beklenen fiyat aralığı (ARCHITECTURE.md §9.6).

ATR tabanlı: ana zaman diliminin ATR14'ü ufka ölçeklenir (`ATR_TF × sqrt(h / TF)`), aralık
`price ± 1.0 × ATR_h` olur. Son 30 günün gerçekleşmiş `h`-getiri dağılımı (q25..q75) varsa ikisinin
ortalaması alınır — tek bir volatilite ölçüsüne bağlı kalmamak için.

Yön kayması yoktur (ilk sürüm): aralık fiyatın etrafında simetriktir. `p_up`'a göre kaydırma ancak
kalibrasyon verisi desteklerse öneri olarak gelir (ROADMAP F8-7).
"""

import math
from dataclasses import dataclass
from typing import Final

import pandas as pd

from marketpulse.core.types import Horizon
from marketpulse.features import indicators as ind
from marketpulse.features.snapshot import FeatureSnapshot

EXPANSION_MULTIPLIER: Final = 1.5  # volatilite genişlemesinde aralık genişler
BASE_MULTIPLIER: Final = 1.0
REALIZED_LOOKBACK_DAYS: Final = 30
MIN_REALIZED_SAMPLES: Final = 30


@dataclass(frozen=True)
class ExpectedRange:
    low: float
    high: float
    source: str  # "atr" | "atr+realized"

    @property
    def width(self) -> float:
        return self.high - self.low


def estimate(
    snapshot: FeatureSnapshot, horizon: Horizon, *, expansion: bool = False
) -> ExpectedRange | None:
    """Beklenen aralık; hesaplanamıyorsa `None` (uydurma aralık üretilmez)."""
    price = snapshot.price
    base = snapshot.frame(horizon.base_interval)
    if price is None or base.empty:
        return None
    atr_series = ind.atr(base, 14).dropna()
    if atr_series.empty:
        return None
    atr_horizon = scale_to_horizon(float(atr_series.iloc[-1]), horizon)
    half_width = atr_horizon
    source = "atr"

    realized = _realized_half_width(base, horizon, price)
    if realized is not None:
        half_width = (atr_horizon + realized) / 2.0
        source = "atr+realized"
    multiplier = EXPANSION_MULTIPLIER if expansion else BASE_MULTIPLIER
    half_width = float(half_width * multiplier)
    return ExpectedRange(
        low=float(price - half_width), high=float(price + half_width), source=source
    )


def scale_to_horizon(atr_value: float, horizon: Horizon) -> float:
    """`ATR_TF × sqrt(ufuk / TF)`: volatilite zamanın kareköküyle büyür."""
    steps = horizon.length / horizon.base_interval.length
    return atr_value * math.sqrt(steps)


def _realized_half_width(base: pd.DataFrame, horizon: Horizon, price: float) -> float | None:
    """Son 30 günün gerçekleşmiş `h`-getirilerinden çeyrekler arası yarı genişlik."""
    steps = int(horizon.length / horizon.base_interval.length)
    bars = int(REALIZED_LOOKBACK_DAYS * 24 * 3600 / horizon.base_interval.length.total_seconds())
    window = base["close"].tail(bars)
    if len(window) <= steps + MIN_REALIZED_SAMPLES:
        return None
    returns = window.pct_change(periods=steps).dropna()
    if len(returns) < MIN_REALIZED_SAMPLES:
        return None
    low_q, high_q = float(returns.quantile(0.25)), float(returns.quantile(0.75))
    return price * (high_q - low_q) / 2.0
