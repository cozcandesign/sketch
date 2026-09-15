"""Binance yanıt biçimleri (resmi dokümandaki alan sırası).

Hem birim testlerinde hem de uçtan uca doğrulama için kullanılan sahte sunucuda kullanılır.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from marketpulse.core.time import to_epoch_ms
from marketpulse.core.types import Interval

EXCHANGE_INFO: dict[str, Any] = {
    "timezone": "UTC",
    "serverTime": 1767225600000,
    "rateLimits": [
        {
            "rateLimitType": "REQUEST_WEIGHT",
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 6000,
        },
        {"rateLimitType": "RAW_REQUESTS", "interval": "MINUTE", "intervalNum": 5, "limit": 61000},
    ],
    "symbols": [
        {"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT"},
        {"symbol": "ETHUSDT", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDT"},
        {"symbol": "SOLUSDT", "status": "TRADING", "baseAsset": "SOL", "quoteAsset": "USDT"},
        {"symbol": "DEADUSDT", "status": "BREAK", "baseAsset": "DEAD", "quoteAsset": "USDT"},
    ],
}


def kline_row(
    open_time: datetime,
    interval: Interval,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 10.0,
) -> list[Any]:
    """Tek bir Binance kline satırı. `closeTime` gerçekte olduğu gibi `open + interval - 1ms`."""
    close_time = open_time + interval.length - timedelta(milliseconds=1)
    return [
        to_epoch_ms(open_time),
        f"{open_:.8f}",
        f"{high:.8f}",
        f"{low:.8f}",
        f"{close:.8f}",
        f"{volume:.8f}",
        to_epoch_ms(close_time),
        f"{volume * close:.8f}",
        120,
        f"{volume / 2:.8f}",
        f"{volume * close / 2:.8f}",
        "0",
    ]


def kline_series(
    start: datetime,
    interval: Interval,
    closes: list[float],
) -> list[list[Any]]:
    """Kapanış fiyatlarından mum serisi üretir (open = önceki kapanış)."""
    rows: list[list[Any]] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_time = start + index * interval.length
        rows.append(
            kline_row(
                open_time,
                interval,
                open_=previous,
                high=max(previous, close) * 1.001,
                low=min(previous, close) * 0.999,
                close=close,
            )
        )
        previous = close
    return rows


def ws_kline_message(
    symbol: str, interval: Interval, open_time: datetime, close: float, *, closed: bool
) -> dict[str, Any]:
    """Combined stream `<symbol>@kline_<interval>` mesajı."""
    return {
        "stream": f"{symbol.lower()}@kline_{interval.value}",
        "data": {
            "e": "kline",
            "E": to_epoch_ms(open_time + interval.length),
            "s": symbol,
            "k": {
                "t": to_epoch_ms(open_time),
                "T": to_epoch_ms(open_time + interval.length - timedelta(milliseconds=1)),
                "s": symbol,
                "i": interval.value,
                "o": f"{close * 0.999:.8f}",
                "c": f"{close:.8f}",
                "h": f"{close * 1.002:.8f}",
                "l": f"{close * 0.998:.8f}",
                "v": "12.5",
                "n": 120,
                "x": closed,
                "q": f"{close * 12.5:.8f}",
                "V": "6.0",
                "Q": f"{close * 6.0:.8f}",
            },
        },
    }


def ws_mini_ticker_message(symbol: str, last: float, open_price: float) -> dict[str, Any]:
    """Combined stream `<symbol>@miniTicker` mesajı."""
    return {
        "stream": f"{symbol.lower()}@miniTicker",
        "data": {
            "e": "24hrMiniTicker",
            "E": to_epoch_ms(datetime(2026, 1, 1, tzinfo=UTC)),
            "s": symbol,
            "c": f"{last:.8f}",
            "o": f"{open_price:.8f}",
            "h": f"{max(last, open_price) * 1.01:.8f}",
            "l": f"{min(last, open_price) * 0.99:.8f}",
            "v": "1234.5",
            "q": f"{last * 1234.5:.8f}",
        },
    }
