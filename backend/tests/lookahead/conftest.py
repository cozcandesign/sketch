"""Look-ahead testleri için ortak veri üreticileri (CLAUDE.md §9)."""

import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from marketpulse.core.types import Interval
from marketpulse.storage import Candle, SqliteRepository, make_engine

SERIES_START = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


def random_walk(
    count: int,
    interval: Interval,
    *,
    seed: int = 7,
    start_price: float = 100.0,
    symbol: str = "BTCUSDT",
    start: datetime = SERIES_START,
) -> list[Candle]:
    """Deterministik rastgele yürüyüş serisi."""
    rng = random.Random(seed)
    candles: list[Candle] = []
    price = start_price
    for index in range(count):
        open_time = start + index * interval.length
        open_price = price
        price = max(1.0, price * (1 + rng.uniform(-0.01, 0.01)))
        candles.append(
            Candle(
                symbol=symbol,
                interval=interval,
                open_time=open_time,
                open=open_price,
                high=max(open_price, price) * 1.001,
                low=min(open_price, price) * 0.999,
                close=price,
                volume=rng.uniform(1, 100),
                quote_volume=price * 10,
                trades=rng.randint(10, 500),
                taker_buy_base=rng.uniform(1, 50),
                close_time=open_time + interval.length,
            )
        )
    return candles


def corrupt_after(candles: list[Candle], as_of: datetime, *, factor: float = 100.0) -> list[Candle]:
    """`as_of` sonrası kapanan mumları bozar. Geçmiş çıktılar bundan etkilenmemeli."""
    return [
        c.model_copy(update={"close": c.close * factor, "high": c.high * factor})
        if c.close_time > as_of
        else c
        for c in candles
    ]
