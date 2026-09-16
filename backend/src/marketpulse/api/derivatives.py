"""Türev metriklerinin okunur özetleri: funding z-skoru, açık pozisyon değişimi, kapsama oranı.

Hem `/market/{symbol}` şeridi hem `/market/{symbol}/orderflow` paneli aynı hesapları kullanır;
iki yerde iki farklı sayı çıkmasın diye tek yerde tutulur.
"""

from datetime import timedelta
from typing import Final

from marketpulse.api.schemas.signals import OpenInterestOut
from marketpulse.storage.models import FundingRate, OpenInterestPoint, OrderflowRow

FUNDING_WINDOW: Final = timedelta(days=30)
OI_WINDOW: Final = timedelta(hours=24)
MIN_FUNDING_SAMPLES: Final = 10


def average_rate(history: list[FundingRate]) -> float | None:
    if not history:
        return None
    return sum(row.rate for row in history) / len(history)


def funding_zscore(current: float | None, history: list[FundingRate]) -> float | None:
    """Anlık funding'in 30 günlük dağılımdaki yeri; dağılım yoksa `None` (sıfır değil)."""
    if current is None or len(history) < MIN_FUNDING_SAMPLES:
        return None
    rates = [row.rate for row in history]
    mean = sum(rates) / len(rates)
    variance = sum((rate - mean) ** 2 for rate in rates) / len(rates)
    if variance <= 0:
        return None
    return float((current - mean) / variance**0.5)


def open_interest_summary(rows: list[OpenInterestPoint]) -> OpenInterestOut:
    """Son açık pozisyon ve pencere başına göre oransal değişim."""
    if not rows:
        return OpenInterestOut(latest=None, ts=None, change_24h=None)
    latest, first = rows[-1], rows[0]
    change = (latest.oi / first.oi - 1.0) if first.oi else None
    return OpenInterestOut(latest=latest.oi, ts=latest.ts, change_24h=change)


def coverage_ratio(flow: list[OrderflowRow], minutes: int) -> float:
    """Penceredeki dakikaların gerçekten dinlenmiş oranı (0..1): kesinti görünür olsun (K22)."""
    if minutes <= 0:
        return 0.0
    listened = sum(row.coverage_seconds or 0.0 for row in flow)
    return round(min(1.0, listened / (minutes * 60.0)), 4)
