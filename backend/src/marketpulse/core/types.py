"""Alan tipleri: ufuk, sembol."""

import re
from datetime import timedelta
from enum import StrEnum
from typing import Final

_SYMBOL_RE: Final = re.compile(r"^[A-Z0-9]{5,20}$")


class Interval(StrEnum):
    """Mum zaman dilimi. Değerler Binance API'siyle ve DB ile aynı."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def length(self) -> timedelta:
        return _INTERVAL_LENGTH[self]


_INTERVAL_LENGTH: Final[dict["Interval", timedelta]] = {}


class Horizon(StrEnum):
    """Tahmin ufku. Değerler API ve DB'de olduğu gibi kullanılır."""

    H30M = "30m"
    H1H = "1h"
    H4H = "4h"
    H24H = "24h"

    @property
    def length(self) -> timedelta:
        """Ufkun süresi."""
        return _LENGTH[self]

    @property
    def cadence(self) -> timedelta:
        """Tahmin sıklığı (K2): 30dk→15dk, 1s→30dk, 4s→1s, 24s→4s."""
        return _CADENCE[self]

    @property
    def label_tr(self) -> str:
        return _LABEL_TR[self]

    @property
    def base_interval(self) -> "Interval":
        """Ufkun ana çalışma zaman dilimi (ARCHITECTURE.md §8.1)."""
        return _BASE_INTERVAL[self]

    @property
    def context_interval(self) -> "Interval":
        """Bağlam zaman dilimi."""
        return _CONTEXT_INTERVAL[self]


_INTERVAL_LENGTH.update(
    {
        Interval.M1: timedelta(minutes=1),
        Interval.M5: timedelta(minutes=5),
        Interval.M15: timedelta(minutes=15),
        Interval.H1: timedelta(hours=1),
        Interval.H4: timedelta(hours=4),
        Interval.D1: timedelta(days=1),
    }
)

_LENGTH: Final[dict[Horizon, timedelta]] = {
    Horizon.H30M: timedelta(minutes=30),
    Horizon.H1H: timedelta(hours=1),
    Horizon.H4H: timedelta(hours=4),
    Horizon.H24H: timedelta(hours=24),
}
_CADENCE: Final[dict[Horizon, timedelta]] = {
    Horizon.H30M: timedelta(minutes=15),
    Horizon.H1H: timedelta(minutes=30),
    Horizon.H4H: timedelta(hours=1),
    Horizon.H24H: timedelta(hours=4),
}
_LABEL_TR: Final[dict[Horizon, str]] = {
    Horizon.H30M: "30 dakika",
    Horizon.H1H: "1 saat",
    Horizon.H4H: "4 saat",
    Horizon.H24H: "24 saat",
}


def parse_symbol(raw: str) -> str:
    """Sembolü normalize eder (büyük harf, boşluksuz) ve biçimini doğrular.

    Binance sembol biçimi: yalnızca büyük harf ve rakam, ör. BTCUSDT. Borsada var mı kontrolü
    burada değil, `exchangeInfo` ile collector'da yapılır.
    """
    symbol = raw.strip().upper()
    if not _SYMBOL_RE.match(symbol):
        msg = f"geçersiz sembol: {raw!r} (beklenen biçim: BTCUSDT)"
        raise ValueError(msg)
    return symbol


_BASE_INTERVAL: Final[dict[Horizon, Interval]] = {
    Horizon.H30M: Interval.M5,
    Horizon.H1H: Interval.M15,
    Horizon.H4H: Interval.H1,
    Horizon.H24H: Interval.H4,
}
_CONTEXT_INTERVAL: Final[dict[Horizon, Interval]] = {
    Horizon.H30M: Interval.M15,
    Horizon.H1H: Interval.H1,
    Horizon.H4H: Interval.H4,
    Horizon.H24H: Interval.D1,
}
