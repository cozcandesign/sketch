from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.types import Horizon
from marketpulse.storage import (
    NewPrediction,
    PredictionOutcome,
    SignalRow,
    SqliteRepository,
    make_engine,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def new_prediction(**overrides: object) -> NewPrediction:
    data: dict[str, object] = {
        "symbol": "BTCUSDT",
        "horizon": Horizon.H1H,
        "as_of": T0,
        "target_at": T0 + timedelta(hours=1),
        "price_at": 50_000.0,
        "p_up": 0.62,
        "confidence": 0.4,
        "confidence_label": "mid",
        "ensemble_version": "baseline-1",
        "non_overlapping": True,
        "source": "baseline",
    }
    data.update(overrides)
    return NewPrediction.model_validate(data)


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


async def test_write_and_read_prediction_with_signals(repo: SqliteRepository) -> None:
    signals = [
        SignalRow(
            module="technical",
            score=0.3,
            confidence=0.5,
            coverage=1.0,
            components={"trend": 0.4},
            rationale=["EMA yapısı yükseliş dizilimi"],
            data_as_of=T0,
        )
    ]
    pid = await repo.write_prediction(
        new_prediction(weights={"technical": 1.0}, report={"headline": "test"}),
        signals,
        created_at=T0,
    )
    stored = await repo.get_prediction(pid)
    assert stored is not None
    assert stored.symbol == "BTCUSDT"
    assert stored.horizon is Horizon.H1H
    assert stored.p_up == 0.62
    assert stored.weights == {"technical": 1.0}
    assert stored.report == {"headline": "test"}
    assert stored.as_of.tzinfo is not None
    assert stored.signals is not None
    assert stored.signals[0].components == {"trend": 0.4}
    assert stored.outcome is None


async def test_due_predictions_only_unresolved_and_past_target(repo: SqliteRepository) -> None:
    past = await repo.write_prediction(new_prediction(), created_at=T0)
    await repo.write_prediction(
        new_prediction(as_of=T0, target_at=T0 + timedelta(hours=4), horizon=Horizon.H4H),
        created_at=T0,
    )
    due = await repo.due_predictions(T0 + timedelta(hours=1))
    assert [p.id for p in due] == [past]

    await repo.write_outcome(
        PredictionOutcome(
            prediction_id=past,
            resolved_at=T0 + timedelta(hours=1),
            price_at_target=50_500.0,
            realized_return=0.01,
            outcome="up",
            hit=True,
            brier=0.1444,
            resolved_by="ws",
        )
    )
    assert await repo.due_predictions(T0 + timedelta(hours=1)) == []


async def test_outcome_write_is_idempotent(repo: SqliteRepository) -> None:
    pid = await repo.write_prediction(new_prediction(), created_at=T0)
    outcome = PredictionOutcome(
        prediction_id=pid,
        resolved_at=T0 + timedelta(hours=1),
        price_at_target=50_500.0,
        realized_return=0.01,
        outcome="up",
        hit=True,
        brier=0.1444,
        resolved_by="ws",
    )
    await repo.write_outcome(outcome)
    await repo.write_outcome(outcome.model_copy(update={"outcome": "down"}))
    stored = await repo.get_prediction(pid)
    assert stored is not None
    assert stored.outcome is not None
    assert stored.outcome.outcome == "up"  # ilk yazım korunur


async def test_list_predictions_filters_and_cursor(repo: SqliteRepository) -> None:
    ids = []
    for index in range(5):
        ids.append(
            await repo.write_prediction(
                new_prediction(
                    as_of=T0 + index * timedelta(minutes=30),
                    target_at=T0 + index * timedelta(minutes=30) + timedelta(hours=1),
                    symbol="BTCUSDT" if index % 2 == 0 else "ETHUSDT",
                ),
                created_at=T0,
            )
        )
    btc = await repo.list_predictions(symbol="BTCUSDT")
    assert [p.id for p in btc] == [ids[4], ids[2], ids[0]]
    page = await repo.list_predictions(limit=2)
    assert [p.id for p in page] == [ids[4], ids[3]]
    next_page = await repo.list_predictions(limit=2, cursor=page[-1].id)
    assert [p.id for p in next_page] == [ids[2], ids[1]]
    assert await repo.list_predictions(horizon=Horizon.H4H) == []


async def test_resolved_rows_skips_unresolved(repo: SqliteRepository) -> None:
    up_id = await repo.write_prediction(new_prediction(p_up=0.7), created_at=T0)
    down_id = await repo.write_prediction(new_prediction(p_up=0.3), created_at=T0)
    missing_id = await repo.write_prediction(new_prediction(p_up=0.5), created_at=T0)
    await repo.write_outcome(
        PredictionOutcome(
            prediction_id=up_id,
            resolved_at=T0,
            price_at_target=1.0,
            realized_return=0.01,
            outcome="up",
            hit=True,
            brier=0.09,
            resolved_by="ws",
        )
    )
    await repo.write_outcome(
        PredictionOutcome(
            prediction_id=down_id,
            resolved_at=T0,
            price_at_target=1.0,
            realized_return=-0.01,
            outcome="down",
            hit=True,
            brier=0.09,
            resolved_by="ws",
        )
    )
    await repo.write_outcome(
        PredictionOutcome(
            prediction_id=missing_id,
            resolved_at=T0,
            price_at_target=None,
            realized_return=None,
            outcome="unresolved",
            hit=None,
            brier=None,
            resolved_by="rest_backfill",
        )
    )
    rows = await repo.resolved_rows()
    assert len(rows) == 2
    assert {r.ensemble_version for r in rows} == {"baseline-1"}
    assert {r.y for r in rows} == {0, 1}
    assert all(r.hit for r in rows)
