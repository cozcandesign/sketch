"""Saklama süreleri (K21): mumlar kalıcı, order flow ve likidasyon 90 gün, outbox 24 saat."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Interval
from marketpulse.engine.retention import run_retention
from marketpulse.storage import Candle, SqliteRepository, make_engine
from marketpulse.storage.models import Liquidation, OrderflowRow

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    repository = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repository.create_all()
    yield repository
    await repository.close()


def liquidation(days_ago: int, side: str) -> Liquidation:
    return Liquidation(
        symbol=SYMBOL,
        ts=NOW - timedelta(days=days_ago),
        side="long" if side == "long" else "short",
        qty=1.0,
        price=60000.0,
        usd=60000.0,
    )


async def test_order_flow_older_than_ninety_days_is_removed(repo: SqliteRepository) -> None:
    await repo.upsert_orderflow(
        [
            OrderflowRow(symbol=SYMBOL, ts=NOW - timedelta(days=100), buy_vol=1.0),
            OrderflowRow(symbol=SYMBOL, ts=NOW - timedelta(days=10), buy_vol=2.0),
        ]
    )

    stats = await run_retention(repo, FakeClock(NOW))

    assert stats.orderflow_pruned == 1
    assert [row.ts for row in await repo.get_orderflow(SYMBOL)] == [NOW - timedelta(days=10)]


async def test_liquidations_follow_the_same_window(repo: SqliteRepository) -> None:
    await repo.insert_liquidations([liquidation(120, "long"), liquidation(5, "short")])

    stats = await run_retention(repo, FakeClock(NOW))

    assert stats.liquidations_pruned == 1
    assert [row.side for row in await repo.get_liquidations(SYMBOL)] == ["short"]


async def test_candles_are_never_deleted(repo: SqliteRepository) -> None:
    """K21: mumlar kalıcıdır. Saklama işi onlara dokunmaz."""
    old = NOW - timedelta(days=900)
    await repo.upsert_candles(
        [
            Candle(
                symbol=SYMBOL,
                interval=Interval.D1,
                open_time=old,
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=10.0,
                close_time=old + Interval.D1.length,
            )
        ]
    )

    await run_retention(repo, FakeClock(NOW))

    assert await repo.count_candles(SYMBOL, Interval.D1) == 1


async def test_nothing_to_prune_is_not_an_error(repo: SqliteRepository) -> None:
    stats = await run_retention(repo, FakeClock(NOW))
    assert stats.total == 0
