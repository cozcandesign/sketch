"""API entegrasyon testleri: TestClient lifespan'ı çalıştırır (migration + relay dahil)."""

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.app import create_app
from marketpulse.config import Settings
from marketpulse.core.clock import FakeClock
from marketpulse.storage import CollectorHealth, SqliteRepository, make_engine
from marketpulse.storage.migrate import schema_ready

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
        outbox_poll_interval_sec=0.02,
        heartbeat_stale_after_sec=60,
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def client(settings: Settings, clock: FakeClock) -> Iterator[TestClient]:
    app = create_app(settings, clock=clock)
    with TestClient(app) as test_client:
        yield test_client


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _seed(settings: Settings, *, heartbeat_at: datetime | None) -> None:
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    if heartbeat_at is not None:
        await repo.write_heartbeat(heartbeat_at, "0.1.0")
    await repo.upsert_collector_health(
        CollectorHealth(collector="spot_klines", status="ok", last_success_at=T0)
    )
    await repo.upsert_collector_health(
        CollectorHealth(collector="rss", status="degraded", last_error="timeout")
    )
    await repo.close()


async def _emit(settings: Settings, topic: str, payload: dict[str, object]) -> None:
    engine = make_engine(settings.db_url)
    repo = SqliteRepository(engine, db_url=settings.db_url)
    await repo.outbox_emit(topic, payload, T0)
    await repo.close()


def test_startup_runs_migrations(client: TestClient, settings: Settings) -> None:
    async def check() -> bool:
        engine = make_engine(settings.db_url)
        try:
            return await schema_ready(engine)
        finally:
            await engine.dispose()

    assert _run(check()) is True


def test_health_without_engine_is_down(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "down"
    assert body["engine"] == {
        "alive": False,
        "last_heartbeat": None,
        "age_seconds": None,
        "version": None,
    }
    assert body["collectors"] == []
    assert body["ws"]["clients"] == 0
    assert body["api_version"] == "0.1.0"
    assert body["server_time"].startswith("2026-01-01T12:00:00")


def test_health_reflects_heartbeat_and_collectors(client: TestClient, settings: Settings) -> None:
    _run(_seed(settings, heartbeat_at=T0 - timedelta(seconds=20)))
    body = client.get("/api/v1/health").json()
    assert body["engine"]["alive"] is True
    assert body["engine"]["age_seconds"] == 20.0
    assert body["engine"]["version"] == "0.1.0"
    assert body["status"] == "degraded"  # rss degraded
    names = [c["collector"] for c in body["collectors"]]
    assert names == ["rss", "spot_klines"]
    assert body["db"]["size_bytes"] > 0


def test_health_stale_heartbeat_is_down(client: TestClient, settings: Settings) -> None:
    _run(_seed(settings, heartbeat_at=T0 - timedelta(seconds=61)))
    body = client.get("/api/v1/health").json()
    assert body["engine"]["alive"] is False
    assert body["status"] == "down"


def test_cors_allows_configured_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_websocket_hello_ping_subscribe_and_relay(client: TestClient, settings: Settings) -> None:
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["op"] == "hello"
        assert hello["api_version"] == "0.1.0"

        ws.send_json({"op": "ping"})
        assert ws.receive_json()["op"] == "pong"

        ws.send_json({"op": "subscribe", "topics": ["health", "signals.*"]})
        assert ws.receive_json() == {"op": "subscribed", "topics": ["health", "signals.*"]}

        ws.send_json({"op": "nope"})
        assert ws.receive_json()["op"] == "error"

        _run(_emit(settings, "alert.created", {"id": 1}))  # abone değil → gelmemeli
        _run(_emit(settings, "health.changed", {"collector": "rss", "status": "ok"}))
        msg = ws.receive_json()
        assert msg["topic"] == "health"
        assert msg["data"] == {"collector": "rss", "status": "ok"}

        _run(_emit(settings, "signals.updated", {"symbol": "BTCUSDT", "horizon": "1h"}))
        msg = ws.receive_json()
        assert msg["topic"] == "signals.BTCUSDT"

        assert client.get("/api/v1/health").json()["ws"]["clients"] == 1
        body = client.get("/api/v1/health").json()
        assert body["outbox"]["last_id"] >= 3

    assert client.get("/api/v1/health").json()["ws"]["clients"] == 0
