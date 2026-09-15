import asyncio
from datetime import UTC, datetime
from typing import Any

import marketpulse.api.outbox_relay as relay_mod
from marketpulse.api.outbox_relay import RelayState, run_outbox_relay, ws_topic_for
from marketpulse.api.ws import WsHub
from marketpulse.core.clock import FakeClock
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.models import OutboxEvent


def test_ws_topic_mapping() -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    assert (
        ws_topic_for(OutboxEvent(id=1, created_at=t0, topic="health.changed", payload={}))
        == "health"
    )
    assert (
        ws_topic_for(
            OutboxEvent(id=2, created_at=t0, topic="signals.updated", payload={"symbol": "ETHUSDT"})
        )
        == "signals.ETHUSDT"
    )
    assert (
        ws_topic_for(OutboxEvent(id=3, created_at=t0, topic="unknown.topic", payload={}))
        == "unknown.topic"
    )


class _FlakyRepo(SqliteRepository):
    """İlk okuma hata verir; relay ölmeden devam etmeli."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.failures_left = 1

    async def outbox_read_after(self, last_id: int, limit: int = 500) -> list[OutboxEvent]:
        if self.failures_left > 0:
            self.failures_left -= 1
            msg = "database is locked"
            raise RuntimeError(msg)
        return await super().outbox_read_after(last_id, limit)


async def test_relay_survives_transient_db_error(monkeypatch: Any) -> None:
    monkeypatch.setattr(relay_mod, "RETRY_DELAY_SEC", 0.01)
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repo = _FlakyRepo(engine)
    await repo.create_all()
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    hub = WsHub()
    state = RelayState()
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_outbox_relay(repo, hub, clock, state, stop, poll_interval=0.01, start_after=0)
    )
    await repo.outbox_emit("alert.created", {"id": 1}, clock.now())
    for _ in range(200):
        await asyncio.sleep(0.01)
        if state.relayed == 1:
            break
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert state.errors == 1
    assert state.relayed == 1
    assert state.last_id == 1
    await repo.close()
