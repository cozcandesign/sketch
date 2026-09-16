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


# --- USDT-M futures (ARCHITECTURE.md §4) ---
# Alan adları ve sıraları Binance futures dokümanındaki örneklerden alınmıştır. Gerçek uca bu
# geliştirme ortamından erişilemediği için doğrulama kullanıcının makinesinde yapılacaktır.

FUTURES_T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def funding_rate_rows(symbol: str = "BTCUSDT", count: int = 3) -> list[dict[str, Any]]:
    """`GET /fapi/v1/fundingRate` — 8 saatte bir gerçekleşen funding."""
    return [
        {
            "symbol": symbol,
            "fundingTime": to_epoch_ms(FUTURES_T0 + timedelta(hours=8 * index)),
            "fundingRate": f"{0.0001 * (index + 1):.8f}",
            "markPrice": f"{60000 + index * 25:.8f}",
        }
        for index in range(count)
    ]


def premium_index(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """`GET /fapi/v1/premiumIndex` — anlık funding göstergesi."""
    return {
        "symbol": symbol,
        "markPrice": "60125.30000000",
        "indexPrice": "60110.10000000",
        "estimatedSettlePrice": "60120.00000000",
        "lastFundingRate": "0.00012500",
        "interestRate": "0.00010000",
        "nextFundingTime": to_epoch_ms(FUTURES_T0 + timedelta(hours=8)),
        "time": to_epoch_ms(FUTURES_T0),
    }


def open_interest_live(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """`GET /fapi/v1/openInterest`."""
    return {
        "openInterest": "76543.210",
        "symbol": symbol,
        "time": to_epoch_ms(FUTURES_T0),
    }


def open_interest_hist_rows(symbol: str = "BTCUSDT", count: int = 3) -> list[dict[str, Any]]:
    """`GET /futures/data/openInterestHist?period=5m`."""
    return [
        {
            "symbol": symbol,
            "sumOpenInterest": f"{76000 + index * 50:.8f}",
            "sumOpenInterestValue": f"{(76000 + index * 50) * 60000:.8f}",
            "timestamp": to_epoch_ms(FUTURES_T0 + timedelta(minutes=5 * index)),
        }
        for index in range(count)
    ]


def long_short_rows(symbol: str = "BTCUSDT", count: int = 3) -> list[dict[str, Any]]:
    """`globalLongShortAccountRatio` / `topLongShortAccountRatio` / `topLongShortPositionRatio`."""
    return [
        {
            "symbol": symbol,
            "longAccount": f"{0.60 + index * 0.01:.4f}",
            "longShortRatio": f"{1.50 + index * 0.05:.4f}",
            "shortAccount": f"{0.40 - index * 0.01:.4f}",
            "timestamp": to_epoch_ms(FUTURES_T0 + timedelta(minutes=5 * index)),
        }
        for index in range(count)
    ]


def taker_volume_rows(count: int = 3) -> list[dict[str, Any]]:
    """`GET /futures/data/takerlongshortRatio` — yanıtta sembol alanı yoktur."""
    return [
        {
            "buySellRatio": f"{1.20 + index * 0.05:.4f}",
            "buyVol": f"{380.0 + index:.4f}",
            "sellVol": f"{310.0 + index:.4f}",
            "timestamp": to_epoch_ms(FUTURES_T0 + timedelta(minutes=5 * index)),
        }
        for index in range(count)
    ]


def ws_agg_trade(
    symbol: str, *, qty: float, price: float, is_buyer_maker: bool, ts: datetime
) -> dict[str, Any]:
    """`<sym>@aggTrade` combined stream mesajı."""
    return {
        "stream": f"{symbol.lower()}@aggTrade",
        "data": {
            "e": "aggTrade",
            "E": to_epoch_ms(ts),
            "s": symbol,
            "a": 123456,
            "p": f"{price:.2f}",
            "q": f"{qty:.4f}",
            "f": 100,
            "l": 105,
            "T": to_epoch_ms(ts),
            "m": is_buyer_maker,
        },
    }


def ws_force_order(
    symbol: str, *, side: str, qty: float, price: float, ts: datetime
) -> dict[str, Any]:
    """`<sym>@forceOrder` mesajı. `side` emir yönüdür: SELL → long tasfiyesi."""
    return {
        "stream": f"{symbol.lower()}@forceOrder",
        "data": {
            "e": "forceOrder",
            "E": to_epoch_ms(ts),
            "o": {
                "s": symbol,
                "S": side,
                "o": "LIMIT",
                "f": "IOC",
                "q": f"{qty:.4f}",
                "p": f"{price:.2f}",
                "ap": f"{price:.2f}",
                "X": "FILLED",
                "l": f"{qty:.4f}",
                "z": f"{qty:.4f}",
                "T": to_epoch_ms(ts),
            },
        },
    }


def ws_depth20(
    symbol: str,
    *,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    ts: datetime,
) -> dict[str, Any]:
    """`<sym>@depth20@100ms` kısmi derinlik mesajı (futures biçimi)."""
    return {
        "stream": f"{symbol.lower()}@depth20@100ms",
        "data": {
            "e": "depthUpdate",
            "E": to_epoch_ms(ts),
            "T": to_epoch_ms(ts),
            "s": symbol,
            "U": 1,
            "u": 2,
            "pu": 0,
            "b": [[f"{p:.2f}", f"{q:.4f}"] for p, q in bids],
            "a": [[f"{p:.2f}", f"{q:.4f}"] for p, q in asks],
        },
    }
