"""Zaman yardımcıları. Projede `datetime.now()` yalnızca burada çağrılır (CLAUDE.md §6).

Tüm datetime değerleri timezone-aware UTC'dir. Naive datetime kabul edilmez.
"""

from datetime import UTC, datetime, timedelta

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def utc_now() -> datetime:
    """Şu an, UTC, timezone-aware."""
    return datetime.now(tz=UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Aware datetime'ı UTC'ye çevirir; naive datetime için ValueError fırlatır."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        msg = f"naive datetime kabul edilmez: {dt!r}. Timezone-aware UTC verin."
        raise ValueError(msg)
    return dt.astimezone(UTC)


def floor_to(dt: datetime, step: timedelta) -> datetime:
    """`dt`'yi epoch'tan itibaren `step` katlarına aşağı yuvarlar (ör. 15 dk ızgarası)."""
    if step <= timedelta(0):
        msg = f"step pozitif olmalı: {step!r}"
        raise ValueError(msg)
    dt = ensure_utc(dt)
    quotient = (dt - EPOCH) // step
    return EPOCH + quotient * step


def floor_to_minute(dt: datetime) -> datetime:
    """Dakikaya aşağı yuvarlar (saniye ve mikrosaniye sıfırlanır)."""
    return floor_to(dt, timedelta(minutes=1))


def is_aligned(dt: datetime, step: timedelta) -> bool:
    """`dt` epoch'tan itibaren `step`'in tam katı mı? Örtüşmesiz tahmin bayrağı bunu kullanır."""
    return floor_to(dt, step) == ensure_utc(dt)


def to_epoch_ms(dt: datetime) -> int:
    """Binance API'nin kullandığı milisaniye epoch."""
    return int(ensure_utc(dt).timestamp() * 1000)


def from_epoch_ms(ms: int) -> datetime:
    """Milisaniye epoch → aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC)
