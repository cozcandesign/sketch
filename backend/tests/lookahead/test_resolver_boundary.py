"""Resolver sınırı: sonuç yalnızca `target_at` anında kapanan mumdan hesaplanır.

CLAUDE.md §9 madde 6 ve 7(c).
"""

from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Horizon, Interval
from marketpulse.storage import Candle, NewPrediction, SqliteRepository
from marketpulse.tracking.ledger import Ledger
from marketpulse.tracking.resolver import Resolver

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
TARGET = T0 + timedelta(hours=1)


def m1(close_time: datetime, close: float) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval=Interval.M1,
        open_time=close_time - timedelta(minutes=1),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
        close_time=close_time,
    )


async def _prediction(repo: SqliteRepository, clock: FakeClock) -> int:
    return await Ledger(repo, clock).record(
        NewPrediction(
            symbol="BTCUSDT",
            horizon=Horizon.H1H,
            as_of=T0,
            target_at=TARGET,
            price_at=100.0,
            p_up=0.7,
            confidence=0.2,
            confidence_label="low",
            ensemble_version="baseline-climatology-1",
            non_overlapping=True,
            source="baseline",
        )
    )


async def test_later_candles_do_not_change_outcome(repo: SqliteRepository) -> None:
    clock = FakeClock(TARGET + timedelta(hours=2))
    pid = await _prediction(repo, clock)
    await repo.upsert_candles(
        [
            m1(TARGET - timedelta(minutes=1), 50.0),  # önceki mum: kullanılmamalı
            m1(TARGET, 110.0),  # doğru mum
            m1(TARGET + timedelta(minutes=1), 9_999.0),  # sonraki mum: kullanılmamalı
            m1(TARGET + timedelta(minutes=30), 1.0),
        ]
    )

    await Resolver(repo, clock).resolve_due()

    stored = await repo.get_prediction(pid)
    assert stored is not None
    assert stored.outcome is not None
    assert stored.outcome.price_at_target == 110.0
    assert stored.outcome.realized_return == pytest.approx(0.10)


async def test_only_exact_close_time_candle_is_used(repo: SqliteRepository) -> None:
    """`target_at` anında kapanan mum yoksa, komşu mumlar sonucu üretemez."""
    clock = FakeClock(TARGET + timedelta(minutes=5))
    await _prediction(repo, clock)
    await repo.upsert_candles(
        [m1(TARGET - timedelta(minutes=1), 120.0), m1(TARGET + timedelta(minutes=1), 130.0)]
    )
    stats = await Resolver(repo, clock).resolve_due()
    assert stats.resolved == 0
    assert stats.waiting == 1
    assert await repo.resolved_rows() == []
