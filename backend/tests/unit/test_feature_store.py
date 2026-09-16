"""FeatureStore: kesme kuralı, kapsama, tazelik, boş veri davranışı."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.types import Interval
from marketpulse.features.feature_store import (
    DEFAULT_LOOKBACK,
    FeatureStore,
    candles_to_frame,
    empty_frame,
)
from marketpulse.storage import Candle, SqliteRepository, make_engine

START = datetime(2026, 1, 1, tzinfo=UTC)
SYMBOL = "BTCUSDT"


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


def make_candles(count: int, interval: Interval, *, start: datetime = START) -> list[Candle]:
    candles: list[Candle] = []
    for index in range(count):
        open_time = start + index * interval.length
        price = 100.0 + index
        candles.append(
            Candle(
                symbol=SYMBOL,
                interval=interval,
                open_time=open_time,
                open=price,
                high=price + 1,
                low=price - 1,
                close=price + 0.5,
                volume=10.0,
                quote_volume=1000.0,
                trades=5,
                taker_buy_base=5.0,
                close_time=open_time + interval.length,
            )
        )
    return candles


async def test_snapshot_only_contains_candles_closed_at_or_before_as_of(
    repo: SqliteRepository,
) -> None:
    """Oluşmakta olan mum asla snapshot'a girmez (CLAUDE.md §9.2)."""
    await repo.upsert_candles(make_candles(20, Interval.M5))
    as_of = START + timedelta(minutes=32)  # 32. dakika: 30. dakikada kapanan mum son kapanan
    store = FeatureStore(repo)
    snapshot = await store.snapshot(SYMBOL, as_of, intervals=[Interval.M5])

    frame = snapshot.frame(Interval.M5)
    assert frame.index.max() == START + timedelta(minutes=30)
    assert (frame.index <= as_of).all()


async def test_snapshot_rejects_a_naive_as_of(repo: SqliteRepository) -> None:
    store = FeatureStore(repo)
    with pytest.raises(ValueError, match="timezone-aware"):
        await store.snapshot(SYMBOL, datetime(2026, 1, 1), intervals=[Interval.M5])  # noqa: DTZ001


async def test_lookback_window_limits_how_far_back_the_snapshot_reaches(
    repo: SqliteRepository,
) -> None:
    await repo.upsert_candles(make_candles(400, Interval.M5))
    as_of = START + 400 * Interval.M5.length
    store = FeatureStore(repo, lookback={Interval.M5: timedelta(hours=2)})
    snapshot = await store.snapshot(SYMBOL, as_of, intervals=[Interval.M5])

    assert snapshot.bars(Interval.M5) == 24  # 2 saat / 5 dk
    assert snapshot.coverage_of(Interval.M5) == pytest.approx(1.0)


async def test_coverage_reports_the_share_of_the_window_that_is_filled(
    repo: SqliteRepository,
) -> None:
    await repo.upsert_candles(make_candles(6, Interval.M5))  # 30 dk veri, pencere 1 saat
    as_of = START + 6 * Interval.M5.length
    store = FeatureStore(repo, lookback={Interval.M5: timedelta(hours=1)})
    snapshot = await store.snapshot(SYMBOL, as_of, intervals=[Interval.M5])

    assert snapshot.coverage_of(Interval.M5) == pytest.approx(0.5)


async def test_missing_interval_is_empty_and_never_raises(repo: SqliteRepository) -> None:
    store = FeatureStore(repo)
    snapshot = await store.snapshot(SYMBOL, START, intervals=[Interval.H4])

    assert snapshot.frame(Interval.H4).empty
    assert snapshot.coverage_of(Interval.H4) == 0.0
    assert snapshot.is_stale(Interval.H4)
    assert snapshot.price is None


async def test_freshness_grows_when_the_stream_stops(repo: SqliteRepository) -> None:
    await repo.upsert_candles(make_candles(10, Interval.M5))
    last_close = START + 10 * Interval.M5.length
    store = FeatureStore(repo)

    fresh = await store.snapshot(SYMBOL, last_close, intervals=[Interval.M5])
    assert not fresh.is_stale(Interval.M5)

    later = last_close + timedelta(minutes=20)
    stale = await store.snapshot(SYMBOL, later, intervals=[Interval.M5])
    assert stale.is_stale(Interval.M5)
    assert stale.freshness["candles_5m"] == pytest.approx(4.0)  # 20 dk / 5 dk


async def test_price_comes_from_the_one_minute_close(repo: SqliteRepository) -> None:
    await repo.upsert_candles(make_candles(5, Interval.M1))
    await repo.upsert_candles(make_candles(5, Interval.H1))
    as_of = START + timedelta(hours=5)
    store = FeatureStore(repo)
    snapshot = await store.snapshot(SYMBOL, as_of, intervals=[Interval.M1, Interval.H1])

    minute_close = snapshot.frame(Interval.M1)["close"].iloc[-1]
    assert snapshot.price == pytest.approx(minute_close)


async def test_snapshot_covers_every_interval_by_default(repo: SqliteRepository) -> None:
    await repo.upsert_candles(make_candles(3, Interval.M15))
    store = FeatureStore(repo)
    snapshot = await store.snapshot(SYMBOL, START + timedelta(days=1))

    assert set(snapshot.candles) == set(Interval)
    assert set(DEFAULT_LOOKBACK) == set(Interval)


def test_frame_is_indexed_by_close_time_and_sorted() -> None:
    frame = candles_to_frame(list(reversed(make_candles(3, Interval.M5))))
    assert frame.index.name == "close_time"
    assert frame.index.is_monotonic_increasing
    assert list(frame.columns)[:5] == ["open_time", "open", "high", "low", "close"]


def test_empty_frame_has_the_same_columns() -> None:
    filled = candles_to_frame(make_candles(2, Interval.M5))
    assert list(empty_frame().columns) == list(filled.columns)
