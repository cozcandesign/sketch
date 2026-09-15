from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Horizon, Interval
from marketpulse.storage import Candle, NewPrediction, SqliteRepository, make_engine
from marketpulse.storage.outbox import Outbox
from marketpulse.tracking.ledger import Ledger
from marketpulse.tracking.resolver import Resolver

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TARGET = T0 + timedelta(hours=1)


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


def m1_candle(close_time: datetime, close: float, symbol: str = "BTCUSDT") -> Candle:
    open_time = close_time - timedelta(minutes=1)
    return Candle(
        symbol=symbol,
        interval=Interval.M1,
        open_time=open_time,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        close_time=close_time,
    )


async def _write_prediction(repo: SqliteRepository, clock: FakeClock, p_up: float = 0.7) -> int:
    return await Ledger(repo, clock).record(
        NewPrediction(
            symbol="BTCUSDT",
            horizon=Horizon.H1H,
            as_of=T0,
            target_at=TARGET,
            price_at=100.0,
            p_up=p_up,
            confidence=0.2,
            confidence_label="low",
            ensemble_version="baseline-climatology-1",
            non_overlapping=True,
            source="baseline",
        )
    )


async def test_resolves_up_with_hit_and_brier(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET)
    pid = await _write_prediction(repo, clock, p_up=0.7)
    await repo.upsert_candles([m1_candle(TARGET, 110.0)])

    stats = await Resolver(repo, clock).resolve_due()

    assert stats.resolved == 1
    stored = await repo.get_prediction(pid)
    assert stored is not None
    assert stored.outcome is not None
    assert stored.outcome.outcome == "up"
    assert stored.outcome.price_at_target == 110.0
    assert stored.outcome.realized_return == pytest.approx(0.10)
    assert stored.outcome.hit is True
    assert stored.outcome.brier == pytest.approx((0.7 - 1) ** 2)
    assert stored.outcome.resolved_by == "ws"


async def test_resolves_down_and_marks_miss(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET)
    pid = await _write_prediction(repo, clock, p_up=0.7)
    await repo.upsert_candles([m1_candle(TARGET, 95.0)])
    await Resolver(repo, clock).resolve_due()
    stored = await repo.get_prediction(pid)
    assert stored is not None
    assert stored.outcome is not None
    assert stored.outcome.outcome == "down"
    assert stored.outcome.hit is False
    assert stored.outcome.brier == pytest.approx(0.49)


async def test_equal_price_counts_as_down(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET)
    await _write_prediction(repo, clock, p_up=0.6)
    await repo.upsert_candles([m1_candle(TARGET, 100.0)])
    await Resolver(repo, clock).resolve_due()
    rows = await repo.resolved_rows()
    assert rows[0].y == 0


async def test_waits_when_candle_missing_inside_grace(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET + timedelta(minutes=2))
    await _write_prediction(repo, clock)
    stats = await Resolver(repo, clock).resolve_due()
    assert stats == type(stats)(resolved=0, unresolved=0, waiting=1, backfilled=0)
    assert await repo.resolved_rows() == []


async def test_uses_rest_backfill_after_grace(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET + timedelta(minutes=11))
    await _write_prediction(repo, clock)
    calls: list[tuple[str, datetime]] = []

    class FakeBackfill:
        async def fetch_candle(self, symbol: str, interval: Interval, close_time: datetime) -> bool:
            calls.append((symbol, close_time))
            await repo.upsert_candles([m1_candle(close_time, 120.0)])
            return True

    stats = await Resolver(repo, clock, backfill=FakeBackfill()).resolve_due()

    assert calls == [("BTCUSDT", TARGET)]
    assert stats.resolved == 1
    assert stats.backfilled == 1
    rows = await repo.resolved_rows()
    assert rows[0].y == 1


async def test_marks_unresolved_after_24h(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET + timedelta(hours=25))
    pid = await _write_prediction(repo, clock)
    stats = await Resolver(repo, clock).resolve_due()
    assert stats.unresolved == 1
    stored = await repo.get_prediction(pid)
    assert stored is not None
    assert stored.outcome is not None
    assert stored.outcome.outcome == "unresolved"
    assert stored.outcome.hit is None
    assert await repo.resolved_rows() == []  # metriklerde sayılmaz


async def test_backfill_failure_does_not_break_resolution(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET + timedelta(minutes=11))
    await _write_prediction(repo, clock)

    class BrokenBackfill:
        async def fetch_candle(self, symbol: str, interval: Interval, close_time: datetime) -> bool:
            msg = "ağ yok"
            raise RuntimeError(msg)

    stats = await Resolver(repo, clock, backfill=BrokenBackfill()).resolve_due()
    assert stats.waiting == 1
    assert stats.resolved == 0


async def test_emits_outcome_event(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET)
    await _write_prediction(repo, clock)
    await repo.upsert_candles([m1_candle(TARGET, 110.0)])
    outbox = Outbox(repo, clock)
    await Resolver(repo, clock, outbox).resolve_due()
    events = await repo.outbox_read_after(0)
    assert [e.topic for e in events] == ["outcome.resolved"]
    assert events[0].payload["outcome"] == "up"
    assert events[0].payload["hit"] is True
