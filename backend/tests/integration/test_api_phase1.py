"""Faz 1 API uçları: tahminler, piyasa durumu, mumlar, kalibrasyon, canlı fiyat."""

import asyncio
import json
from collections.abc import AsyncIterator, Coroutine, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.app import create_app
from marketpulse.config import Settings
from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Horizon, Interval
from marketpulse.storage import (
    Candle,
    NewPrediction,
    PredictionOutcome,
    SqliteRepository,
    make_engine,
)
from tests.fixtures.binance import ws_mini_ticker_message

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
        outbox_poll_interval_sec=0.02,
        symbols=["BTCUSDT", "ETHUSDT"],
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def client(settings: Settings, clock: FakeClock) -> Iterator[TestClient]:
    app = create_app(settings, clock=clock, live_prices=False)
    with TestClient(app) as test_client:
        yield test_client


def candle(
    symbol: str, close_time: datetime, close: float, interval: Interval = Interval.M1
) -> Candle:
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=close_time - interval.length,
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=12.5,
        close_time=close_time,
    )


async def _seed(settings: Settings) -> dict[str, int]:
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    await repo.upsert_candles(
        [candle("BTCUSDT", T0 - timedelta(hours=24), 60_000.0), candle("BTCUSDT", T0, 63_000.0)]
        + [
            candle("BTCUSDT", T0 - i * Interval.M15.length, 60_000.0 + i, Interval.M15)
            for i in range(5)
        ]
    )
    ids: dict[str, int] = {}
    for index, (version, p_up, outcome_label) in enumerate(
        [
            ("baseline-climatology-1", 0.7, "up"),
            ("baseline-momentum-1", 0.4, "down"),
            ("baseline-climatology-1", 0.6, None),
        ]
    ):
        as_of = T0 - timedelta(hours=3 - index)
        pid = await repo.write_prediction(
            NewPrediction(
                symbol="BTCUSDT",
                horizon=Horizon.H1H,
                as_of=as_of,
                target_at=as_of + timedelta(hours=1),
                price_at=60_000.0,
                p_up=p_up,
                confidence=0.2,
                confidence_label="low",
                ensemble_version=version,
                non_overlapping=True,
                source="baseline",
                report={"headline": "referans tahmin"},
            ),
            created_at=as_of,
        )
        ids[f"{version}-{index}"] = pid
        if outcome_label is not None:
            y = 1 if outcome_label == "up" else 0
            await repo.write_outcome(
                PredictionOutcome(
                    prediction_id=pid,
                    resolved_at=as_of + timedelta(hours=1),
                    price_at_target=61_000.0 if y else 59_000.0,
                    realized_return=0.0167 if y else -0.0167,
                    outcome=outcome_label,  # type: ignore[arg-type]
                    hit=(p_up > 0.5) == bool(y),
                    brier=(p_up - y) ** 2,
                    resolved_by="ws",
                )
            )
    await repo.close()
    return ids


def test_symbols_endpoint(client: TestClient) -> None:
    body = client.get("/api/v1/symbols").json()
    assert body["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert body["timezone"] == "Europe/Istanbul"


def test_market_state_reports_price_change_and_coverage(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    body = client.get("/api/v1/market/BTCUSDT").json()
    assert body["symbol"] == "BTCUSDT"
    assert body["price"]["last"] == 63_000.0
    assert body["price"]["change_24h"] == pytest.approx(0.05)
    assert body["price"]["stale"] is False
    coverage = {c["interval"]: c["count"] for c in body["coverage"]}
    assert coverage["1m"] == 2
    assert coverage["15m"] == 5
    horizons = {h["horizon"]: h for h in body["horizons"]}
    assert set(horizons) == {"30m", "1h", "4h", "24h"}
    assert horizons["1h"]["label_tr"] == "1 saat"
    assert len(horizons["1h"]["predictions"]) == 3
    assert horizons["30m"]["predictions"] == []


def test_market_rejects_unknown_symbol(client: TestClient) -> None:
    assert client.get("/api/v1/market/DOGEUSDT").status_code == 404


def test_market_price_is_stale_without_recent_candle(
    client: TestClient, settings: Settings, clock: FakeClock
) -> None:
    _run(_seed(settings))
    clock.advance(timedelta(minutes=10))
    body = client.get("/api/v1/market/BTCUSDT").json()
    assert body["price"]["stale"] is True


def test_candles_endpoint_returns_chart_format(client: TestClient, settings: Settings) -> None:
    _run(_seed(settings))
    body = client.get("/api/v1/market/BTCUSDT/candles?interval=15m&limit=3").json()
    assert body["interval"] == "15m"
    assert len(body["candles"]) == 3
    times = [c["time"] for c in body["candles"]]
    assert times == sorted(times)  # artan zaman: grafik kütüphanesinin şartı
    assert isinstance(times[0], int)


def test_predictions_list_filters_and_pagination(client: TestClient, settings: Settings) -> None:
    _run(_seed(settings))
    page = client.get("/api/v1/predictions?limit=2").json()
    assert len(page["items"]) == 2
    assert page["next_cursor"] is not None
    rest = client.get(f"/api/v1/predictions?limit=2&cursor={page['next_cursor']}").json()
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None

    active = client.get("/api/v1/predictions?status=active").json()
    assert len(active["items"]) == 1
    assert active["items"][0]["outcome"] is None

    resolved = client.get("/api/v1/predictions?status=resolved").json()
    assert len(resolved["items"]) == 2
    assert {item["outcome"]["outcome"] for item in resolved["items"]} == {"up", "down"}
    assert {item["model_version"] for item in resolved["items"]} == {
        "baseline-climatology-1",
        "baseline-momentum-1",
    }
    assert client.get("/api/v1/predictions?horizon=4h").json()["items"] == []


def test_prediction_detail_and_404(client: TestClient, settings: Settings) -> None:
    ids = _run(_seed(settings))
    any_id = next(iter(ids.values()))
    body = client.get(f"/api/v1/predictions/{any_id}").json()
    assert body["id"] == any_id
    assert body["report"]["headline"] == "referans tahmin"
    assert body["signals"] == []  # Faz 1: referans tahmincinin modül kırılımı yok
    assert client.get("/api/v1/predictions/99999").status_code == 404


def test_calibration_summarizes_by_model_and_horizon(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    body = client.get("/api/v1/calibration?window=all").json()
    assert body["overall"]["n"] == 2
    assert body["overall"]["hit_rate"] == 1.0
    assert body["overall"]["brier"] == pytest.approx((0.09 + 0.16) / 2)
    assert body["pending"] == 1
    models = {m["model_version"]: m for m in body["by_model"]}
    assert models["baseline-climatology-1"]["n"] == 1
    assert models["baseline-climatology-1"]["label_tr"] == "Referans: taban oranı"
    assert [h["horizon"] for h in body["by_horizon"]] == ["1h"]
    assert len(body["bins"]) == 10
    assert sum(b["n"] for b in body["bins"]) == 2
    assert len(body["daily"]) >= 1


def test_calibration_empty_is_safe(client: TestClient) -> None:
    body = client.get("/api/v1/calibration").json()
    assert body["overall"]["n"] == 0
    assert body["overall"]["brier"] is None
    assert body["by_model"] == []
    assert sum(b["n"] for b in body["bins"]) == 0


def test_live_relay_broadcasts_price_to_subscribers(settings: Settings, clock: FakeClock) -> None:
    """Sahte miniTicker akışı → `price.BTCUSDT` konusuna yayın."""
    messages = [
        json.dumps(ws_mini_ticker_message("BTCUSDT", 63_000.0, 60_000.0)),
        json.dumps(ws_mini_ticker_message("ETHUSDT", 3_300.0, 3_000.0)),
    ]

    @asynccontextmanager
    async def fake_connect(_url: str) -> AsyncIterator[AsyncIterator[str]]:
        async def stream() -> AsyncIterator[str]:
            # Sürekli akış: istemci abone olmadan önceki mesajlar kimseye gitmez.
            # Saati ilerletiyoruz ki hız sınırlaması (throttle) mesajları susturmasın.
            while True:
                for message in messages:
                    clock.advance(timedelta(seconds=1))
                    yield message
                await asyncio.sleep(0.01)

        yield stream()

    app = create_app(settings, clock=clock, live_prices=True, connect=fake_connect)
    with TestClient(app) as test_client, test_client.websocket_connect("/ws") as ws:
        ws.receive_json()  # hello
        ws.send_json({"op": "subscribe", "topics": ["price.BTCUSDT"]})
        assert ws.receive_json()["op"] == "subscribed"
        message = ws.receive_json()
        assert message["topic"] == "price.BTCUSDT"
        assert message["data"]["price"] == 63_000.0
        assert message["data"]["change24h"] == pytest.approx(0.05)
        assert message["data"]["stale"] is False
        health = test_client.get("/api/v1/health").json()
        assert health["live_prices"]["messages"] >= 1
