from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from marketpulse.collectors.binance_client import BinanceClient, BinanceError
from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Interval
from marketpulse.engine.ratelimit import RateLimiter
from tests.fixtures.binance import EXCHANGE_INFO, kline_series

BASE = "https://api.test.invalid"
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _client(clock: FakeClock) -> tuple[BinanceClient, list[float]]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock.advance(timedelta(seconds=seconds))

    limiter = RateLimiter(clock, limit=6000, sleep=sleep)  # type: ignore[arg-type]
    return BinanceClient(BASE, limiter, sleep=sleep, backoff_base_sec=0.1), slept


@respx.mock
async def test_klines_parsed_and_close_time_normalized() -> None:
    clock = FakeClock(T0)
    client, _ = _client(clock)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = kline_series(start, Interval.M1, [100.0, 101.0, 100.5])
    respx.get(f"{BASE}/api/v3/klines").mock(return_value=httpx.Response(200, json=rows))

    candles = await client.klines("BTCUSDT", Interval.M1, start=start)

    assert len(candles) == 3
    first = candles[0]
    assert first.symbol == "BTCUSDT"
    assert first.interval is Interval.M1
    assert first.open_time == start
    # Binance closeTime = open + 1dk - 1ms; biz open + 1dk saklarız
    assert first.close_time == start + timedelta(minutes=1)
    assert first.close == 100.0
    assert candles[1].close == 101.0
    assert candles[1].is_green
    await client.aclose()


@respx.mock
async def test_klines_sends_symbol_interval_and_time_params() -> None:
    clock = FakeClock(T0)
    client, _ = _client(clock)
    route = respx.get(f"{BASE}/api/v3/klines").mock(return_value=httpx.Response(200, json=[]))
    await client.klines("ETHUSDT", Interval.H1, start=T0, end=T0 + timedelta(hours=5), limit=5000)
    request = route.calls[0].request
    assert request.url.params["symbol"] == "ETHUSDT"
    assert request.url.params["interval"] == "1h"
    assert request.url.params["limit"] == "1000"  # üst sınıra kırpılır
    assert request.url.params["startTime"] == str(int(T0.timestamp() * 1000))
    await client.aclose()


@respx.mock
async def test_weight_limit_and_symbols_from_exchange_info() -> None:
    clock = FakeClock(T0)
    client, _ = _client(clock)
    respx.get(f"{BASE}/api/v3/exchangeInfo").mock(
        return_value=httpx.Response(200, json=EXCHANGE_INFO)
    )
    limit = await client.weight_limit()
    assert limit is not None
    assert limit.limit == 6000
    assert limit.window == timedelta(minutes=1)
    symbols = await client.symbols()
    assert {"BTCUSDT", "ETHUSDT", "SOLUSDT"} <= symbols
    assert "DEADUSDT" not in symbols  # TRADING değil
    await client.aclose()


@respx.mock
async def test_used_weight_header_syncs_limiter() -> None:
    clock = FakeClock(T0)
    client, _ = _client(clock)
    respx.get(f"{BASE}/api/v3/time").mock(
        return_value=httpx.Response(
            200, json={"serverTime": 1767225600000}, headers={"x-mbx-used-weight-1m": "4321"}
        )
    )
    await client.server_time()
    assert client._limiter.used == 4321
    await client.aclose()


@respx.mock
async def test_retries_on_server_error_then_succeeds() -> None:
    clock = FakeClock(T0)
    client, slept = _client(clock)
    respx.get(f"{BASE}/api/v3/time").mock(
        side_effect=[
            httpx.Response(503, text="maintenance"),
            httpx.Response(200, json={"serverTime": 1767225600000}),
        ]
    )
    when = await client.server_time()
    assert when.year == 2026
    assert len(slept) == 1  # bir kez backoff
    await client.aclose()


@respx.mock
async def test_429_blocks_limiter_and_retries() -> None:
    clock = FakeClock(T0)
    client, _ = _client(clock)
    respx.get(f"{BASE}/api/v3/time").mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "7"}, text="too many"),
            httpx.Response(200, json={"serverTime": 1767225600000}),
        ]
    )
    await client.server_time()
    assert clock.now() >= T0 + timedelta(seconds=7)  # ban süresi beklendi
    await client.aclose()


@respx.mock
async def test_418_ban_is_respected() -> None:
    clock = FakeClock(T0)
    client, _ = _client(clock)
    respx.get(f"{BASE}/api/v3/time").mock(
        return_value=httpx.Response(418, headers={"retry-after": "60"}, text="banned")
    )
    with pytest.raises(BinanceError):
        await client.server_time()
    assert clock.now() >= T0 + timedelta(seconds=60)
    await client.aclose()


@respx.mock
async def test_client_error_raises_without_retry() -> None:
    clock = FakeClock(T0)
    client, slept = _client(clock)
    route = respx.get(f"{BASE}/api/v3/klines").mock(
        return_value=httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
    )
    with pytest.raises(BinanceError, match="400"):
        await client.klines("NOPE", Interval.M1)
    assert route.call_count == 1
    assert slept == []
    await client.aclose()


@respx.mock
async def test_connection_error_is_retried_then_raises() -> None:
    clock = FakeClock(T0)
    client, slept = _client(clock)
    respx.get(f"{BASE}/api/v3/time").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(BinanceError, match="başarısız"):
        await client.server_time()
    assert len(slept) == 4
    await client.aclose()
