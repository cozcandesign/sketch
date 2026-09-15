"""Saat soyutlaması: üretimde sistem saati, testte kontrol edilebilir sahte saat."""

from datetime import datetime, timedelta
from typing import Protocol

from marketpulse.core.time import ensure_utc, utc_now


class Clock(Protocol):
    """Zaman kaynağı. Engine ve api her yerde bunu kullanır; `utc_now()` doğrudan çağrılmaz."""

    def now(self) -> datetime: ...


class SystemClock:
    """Gerçek saat."""

    def now(self) -> datetime:
        return utc_now()


class FakeClock:
    """Testler için elle ilerletilen saat."""

    def __init__(self, start: datetime) -> None:
        self._now = ensure_utc(start)

    def now(self) -> datetime:
        return self._now

    def set(self, dt: datetime) -> None:
        self._now = ensure_utc(dt)

    def advance(self, delta: timedelta) -> datetime:
        self._now = self._now + delta
        return self._now
