"""`/signals/{symbol}` ve `/market/{symbol}/levels` uçları."""

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.app import create_app
from marketpulse.config import Settings
from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Horizon, Interval
from marketpulse.engine.predict import LivePredictor
from marketpulse.features.feature_store import FeatureStore
from marketpulse.storage import Candle, Outbox, SqliteRepository, make_engine
from marketpulse.tracking.ledger import Ledger

AS_OF = datetime(2026, 2, 20, tzinfo=UTC)
SYMBOL = "BTCUSDT"
INTERVALS = (Interval.M1, Interval.M5, Interval.M15, Interval.H1, Interval.H4, Interval.D1)


def candles(interval: Interval, count: int) -> list[Candle]:
    rows: list[Candle] = []
    for index in range(count):
        open_time = AS_OF - (count - index) * interval.length
        wave = 1.0 + 0.01 * ((index % 20) - 10) / 10.0
        price = 100.0 * wave * (1 + 0.0005 * index)
        rows.append(
            Candle(
                symbol=SYMBOL,
                interval=interval,
                open_time=open_time,
                open=price,
                high=price * 1.004,
                low=price * 0.996,
                close=price * 1.001,
                volume=10.0 + (index % 7),
                quote_volume=1000.0,
                trades=15,
                taker_buy_base=5.0,
                close_time=open_time + interval.length,
            )
        )
    return rows


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _seed(settings: Settings) -> None:
    """Şema, uygulama açılışında migration ile kurulur; burada yalnızca veri yazılır."""
    repo = SqliteRepository(make_engine(settings.db_url), db_url=settings.db_url)
    for interval in INTERVALS:
        await repo.upsert_candles(candles(interval, 320))
    clock = FakeClock(AS_OF)
    outbox = Outbox(repo, clock)
    predictor = LivePredictor(repo, Ledger(repo, clock, outbox), FeatureStore(repo), outbox=outbox)
    for horizon in Horizon:
        await predictor.run(symbols=[SYMBOL], horizon=horizon, as_of=AS_OF)
    await repo.close()


async def _outbox_topics(settings: Settings) -> list[tuple[str, dict[str, Any]]]:
    repo = SqliteRepository(make_engine(settings.db_url), db_url=settings.db_url)
    events = await repo.outbox_read_after(0)
    await repo.close()
    return [(event.topic, event.payload) for event in events]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'signals.db'}",
        symbols=[SYMBOL],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, clock=FakeClock(AS_OF), live_prices=False)
    with TestClient(app) as test_client:
        yield test_client


def test_signals_endpoint_returns_a_module_breakdown_per_horizon(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    response = client.get(f"/api/v1/signals/{SYMBOL}")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == SYMBOL
    assert [h["horizon"] for h in body["horizons"]] == [h.value for h in Horizon]
    for horizon in body["horizons"]:
        assert horizon["p_up"] is not None
        modules = {module["module"]: module for module in horizon["modules"]}
        assert set(modules) == {"technical", "orderflow"}
        technical = modules["technical"]
        assert -1.0 <= technical["score"] <= 1.0
        assert technical["rationale"]
        assert horizon["report"]["headline"]


def test_signals_endpoint_is_empty_but_valid_before_any_prediction(client: TestClient) -> None:
    body = client.get(f"/api/v1/signals/{SYMBOL}").json()
    assert all(h["modules"] == [] for h in body["horizons"])
    assert all(h["p_up"] is None for h in body["horizons"])


def test_unknown_symbols_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/signals/DOGEUSDT").status_code == 404
    assert client.get("/api/v1/market/DOGEUSDT/levels").status_code == 404


def test_levels_endpoint_returns_mechanical_levels_and_a_volume_profile(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    response = client.get(f"/api/v1/market/{SYMBOL}/levels", params={"interval": "15m"})
    assert response.status_code == 200
    body = response.json()
    assert body["interval"] == "15m"
    assert body["price"] > 0
    assert body["atr"] > 0
    assert body["levels"]
    distances = [level["distance_atr"] for level in body["levels"]]
    assert distances == sorted(distances)  # en yakın seviye başta
    for level in body["levels"]:
        assert level["kind"] in {"high", "low"}
        assert level["touches"] >= 1
    profile = body["volume_profile"]
    assert profile["value_area_low"] <= profile["poc"] <= profile["value_area_high"]


def test_levels_endpoint_survives_a_symbol_without_candles(client: TestClient) -> None:
    body = client.get(f"/api/v1/market/{SYMBOL}/levels").json()
    assert body["levels"] == []
    assert body["volume_profile"] is None
    assert body["price"] is None


def test_the_signals_updated_event_is_emitted_for_the_websocket(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    updates = [
        payload for topic, payload in _run(_outbox_topics(settings)) if topic == "signals.updated"
    ]
    assert len(updates) == len(Horizon)
    assert updates[0]["symbol"] == SYMBOL
    assert updates[0]["modules"][0]["module"] == "technical"
