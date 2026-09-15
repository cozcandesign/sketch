from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.types import Interval
from marketpulse.storage import Candle, CandleGap, SqliteRepository, make_engine

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def candle(index: int, close: float, interval: Interval = Interval.M1) -> Candle:
    open_time = T0 + index * interval.length
    return Candle(
        symbol="BTCUSDT",
        interval=interval,
        open_time=open_time,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=10.0,
        quote_volume=10.0 * close,
        trades=5,
        taker_buy_base=5.0,
        close_time=open_time + interval.length,
    )


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


async def test_upsert_is_idempotent_and_updates(repo: SqliteRepository) -> None:
    assert await repo.upsert_candles([candle(0, 100), candle(1, 101)]) == 2
    await repo.upsert_candles([candle(1, 999)])  # aynı anahtar → güncelle
    assert await repo.count_candles("BTCUSDT", Interval.M1) == 2
    candles = await repo.get_candles("BTCUSDT", Interval.M1)
    assert [c.close for c in candles] == [100, 999]


async def test_get_candles_as_of_returns_only_closed(repo: SqliteRepository) -> None:
    await repo.upsert_candles([candle(i, 100 + i) for i in range(5)])
    # 3. mum 00:03'te açılır, 00:04'te kapanır: as_of=00:04 iken dahil, 00:03'te değil
    at_0403 = await repo.get_candles("BTCUSDT", Interval.M1, as_of=T0 + timedelta(minutes=4))
    assert [c.open_time for c in at_0403] == [T0 + i * timedelta(minutes=1) for i in range(4)]
    at_0300 = await repo.get_candles("BTCUSDT", Interval.M1, as_of=T0 + timedelta(minutes=3))
    assert len(at_0300) == 3


async def test_get_candles_limit_returns_newest_in_ascending_order(repo: SqliteRepository) -> None:
    await repo.upsert_candles([candle(i, 100 + i) for i in range(10)])
    candles = await repo.get_candles("BTCUSDT", Interval.M1, limit=3)
    assert [c.close for c in candles] == [107, 108, 109]


async def test_candle_closing_at_and_latest(repo: SqliteRepository) -> None:
    await repo.upsert_candles([candle(i, 100 + i) for i in range(3)])
    exact = await repo.get_candle_closing_at("BTCUSDT", Interval.M1, T0 + timedelta(minutes=2))
    assert exact is not None
    assert exact.close == 101  # 00:01 açılan mum 00:02'de kapanır
    assert await repo.get_candle_closing_at("BTCUSDT", Interval.M1, T0) is None
    latest = await repo.latest_candle("BTCUSDT", Interval.M1)
    assert latest is not None
    assert latest.close == 102
    bounded = await repo.latest_candle("BTCUSDT", Interval.M1, as_of=T0 + timedelta(minutes=1))
    assert bounded is not None
    assert bounded.close == 100


async def test_find_candle_gaps(repo: SqliteRepository) -> None:
    present = [candle(i, 100 + i) for i in (0, 1, 4, 5, 9)]
    await repo.upsert_candles(present)
    gaps = await repo.find_candle_gaps(
        "BTCUSDT", Interval.M1, since=T0, until=T0 + timedelta(minutes=10)
    )
    assert gaps == [
        CandleGap(T0 + timedelta(minutes=2), T0 + timedelta(minutes=4)),
        CandleGap(T0 + timedelta(minutes=6), T0 + timedelta(minutes=9)),
    ]


async def test_no_gaps_when_series_complete(repo: SqliteRepository) -> None:
    await repo.upsert_candles([candle(i, 100 + i) for i in range(5)])
    gaps = await repo.find_candle_gaps(
        "BTCUSDT", Interval.M1, since=T0, until=T0 + timedelta(minutes=5)
    )
    assert gaps == []


async def test_intervals_are_isolated(repo: SqliteRepository) -> None:
    await repo.upsert_candles([candle(0, 100, Interval.M1), candle(0, 200, Interval.H1)])
    assert await repo.count_candles("BTCUSDT", Interval.M1) == 1
    hourly = await repo.get_candles("BTCUSDT", Interval.H1)
    assert hourly[0].close == 200
    assert hourly[0].close_time == T0 + timedelta(hours=1)
