import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from marketpulse.collectors.binance_client import BinanceClient
from marketpulse.collectors.klines import KlinesCollector
from marketpulse.collectors.klines_ws import KlinesWsCollector, parse_ws_kline
from marketpulse.collectors.ws_stream import combined_url
from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Interval
from marketpulse.engine.health import HealthRegistry
from marketpulse.engine.ratelimit import RateLimiter
from marketpulse.storage import SqliteRepository, make_engine
from tests.fixtures.binance import kline_series, ws_kline_message

BASE = "https://api.test.invalid"
WS_BASE = "wss://stream.test.invalid/stream"
NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


def _client(clock: FakeClock) -> BinanceClient:
    async def sleep(seconds: float) -> None:
        clock.advance(timedelta(seconds=seconds))

    return BinanceClient(BASE, RateLimiter(clock, sleep=sleep), sleep=sleep)  # type: ignore[arg-type]


@respx.mock
async def test_backfill_writes_only_closed_candles(repo: SqliteRepository) -> None:
    clock = FakeClock(NOW)
    collector = KlinesCollector(
        _client(clock), repo, clock, symbols=["BTCUSDT"], intervals=[Interval.H1]
    )
    start = NOW - timedelta(hours=3)
    rows = kline_series(start, Interval.H1, [100.0, 101.0, 102.0])
    # Son satır oluşmakta olan mum: close_time > NOW
    rows.append(kline_series(NOW, Interval.H1, [103.0])[0])
    respx.get(f"{BASE}/api/v3/klines").mock(return_value=httpx.Response(200, json=rows))

    written = await collector.backfill(lookback={Interval.H1: timedelta(hours=3)})

    assert written == 3
    stored = await repo.get_candles("BTCUSDT", Interval.H1)
    assert [c.close for c in stored] == [100.0, 101.0, 102.0]
    assert all(c.close_time <= NOW for c in stored)


@respx.mock
async def test_backfill_paginates_until_range_covered(repo: SqliteRepository) -> None:
    clock = FakeClock(NOW)
    collector = KlinesCollector(
        _client(clock), repo, clock, symbols=["BTCUSDT"], intervals=[Interval.M1], page_limit=2
    )
    start = NOW - timedelta(minutes=5)
    page_one = kline_series(start, Interval.M1, [100.0, 101.0])
    page_two = kline_series(start + timedelta(minutes=2), Interval.M1, [102.0, 103.0])
    page_three = kline_series(start + timedelta(minutes=4), Interval.M1, [104.0])
    respx.get(f"{BASE}/api/v3/klines").mock(
        side_effect=[
            httpx.Response(200, json=page_one),
            httpx.Response(200, json=page_two),
            httpx.Response(200, json=page_three),
        ]
    )
    written = await collector.backfill(lookback={Interval.M1: timedelta(minutes=5)})
    assert written == 5
    assert await repo.count_candles("BTCUSDT", Interval.M1) == 5


@respx.mock
async def test_fill_gaps_requests_only_missing_range(repo: SqliteRepository) -> None:
    clock = FakeClock(NOW)
    start = NOW - timedelta(minutes=5)
    existing = kline_series(start, Interval.M1, [100.0, 101.0, 102.0, 103.0, 104.0])
    client = _client(clock)
    # Önce beş mumu yaz, sonra ortadakini sil
    respx.get(f"{BASE}/api/v3/klines").mock(return_value=httpx.Response(200, json=existing))
    collector = KlinesCollector(client, repo, clock, symbols=["BTCUSDT"], intervals=[Interval.M1])
    await collector.backfill(lookback={Interval.M1: timedelta(minutes=5)})
    await repo.delete_candles_before(Interval.M1, start + timedelta(minutes=1))
    respx.get(f"{BASE}/api/v3/klines").mock(return_value=httpx.Response(200, json=existing[:1]))

    filled = await collector.fill_gaps()

    assert filled == 1
    assert await repo.count_candles("BTCUSDT", Interval.M1) == 5


def test_parse_ws_kline_ignores_open_candle() -> None:
    open_time = datetime(2026, 1, 1, tzinfo=UTC)
    open_msg = ws_kline_message("BTCUSDT", Interval.M1, open_time, 100.0, closed=False)
    assert parse_ws_kline(open_msg) is None

    closed = parse_ws_kline(ws_kline_message("BTCUSDT", Interval.M1, open_time, 100.0, closed=True))
    assert closed is not None
    assert closed.symbol == "BTCUSDT"
    assert closed.close == 100.0
    assert closed.close_time == open_time + timedelta(minutes=1)


def test_combined_url_builds_stream_list() -> None:
    url = combined_url(WS_BASE, ["btcusdt@kline_1m", "ethusdt@kline_1m"])
    assert url == f"{WS_BASE}?streams=btcusdt@kline_1m/ethusdt@kline_1m"
    with pytest.raises(ValueError, match="en az bir"):
        combined_url(WS_BASE, [])


def _fake_connect(messages: list[str]):
    @asynccontextmanager
    async def factory(_url: str) -> AsyncIterator[AsyncIterator[str]]:
        async def stream() -> AsyncIterator[str]:
            for message in messages:
                yield message

        yield stream()

    return factory


async def test_ws_collector_writes_closed_candles_only(repo: SqliteRepository) -> None:
    clock = FakeClock(NOW)
    health = HealthRegistry(clock)
    open_time = NOW - timedelta(minutes=2)
    messages = [
        json.dumps(ws_kline_message("BTCUSDT", Interval.M1, open_time, 100.0, closed=False)),
        json.dumps(ws_kline_message("BTCUSDT", Interval.M1, open_time, 100.5, closed=True)),
        "bozuk json",
        json.dumps({"stream": "x", "data": {"e": "other"}}),
        json.dumps(
            ws_kline_message(
                "ETHUSDT", Interval.M1, open_time + timedelta(minutes=1), 3000.0, closed=True
            )
        ),
    ]
    collector = KlinesWsCollector(
        WS_BASE,
        repo,
        clock,
        health,
        symbols=["BTCUSDT", "ETHUSDT"],
        connect=_fake_connect(messages),
    )

    await collector.run(asyncio.Event())

    assert collector.written == 2
    btc = await repo.get_candles("BTCUSDT", Interval.M1)
    assert [c.close for c in btc] == [100.5]
    eth = await repo.get_candles("ETHUSDT", Interval.M1)
    assert [c.close for c in eth] == [3000.0]
    assert health.status_of("klines_ws") == "ok"


async def test_ws_collector_returns_for_planned_reconnect(repo: SqliteRepository) -> None:
    clock = FakeClock(NOW)
    health = HealthRegistry(clock)
    messages = [
        json.dumps(
            ws_kline_message("BTCUSDT", Interval.M1, NOW - timedelta(minutes=i), 100.0, closed=True)
        )
        for i in range(1, 4)
    ]
    collector = KlinesWsCollector(
        WS_BASE,
        repo,
        clock,
        health,
        symbols=["BTCUSDT"],
        connect=_fake_connect(messages),
        planned_reconnect=timedelta(0),  # ilk mesajdan sonra dön
    )
    await collector.run(asyncio.Event())
    assert collector.written == 1
