"""Outbox → WebSocket relay (ARCHITECTURE.md §2). Api sürecinde arka plan görevi."""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from marketpulse.api.ws import WsHub
from marketpulse.core.clock import Clock
from marketpulse.storage.models import OutboxEvent
from marketpulse.storage.outbox import Outbox
from marketpulse.storage.repository import Repository

# outbox topic -> ws topic (sembol bazlı olanlar payload'dan türetilir)
TOPIC_MAP: dict[str, str] = {
    "prediction.created": "predictions",
    "outcome.resolved": "outcomes",
    "news.classified": "news",
    "alert.created": "alerts",
    "health.changed": "health",
    "costs.updated": "costs",
    "settings.changed": "settings",
}


def ws_topic_for(event: OutboxEvent) -> str:
    if event.topic == "signals.updated":
        symbol = event.payload.get("symbol", "")
        return f"signals.{symbol}" if symbol else "signals"
    return TOPIC_MAP.get(event.topic, event.topic)


@dataclass
class RelayState:
    """Sağlık endpoint'i için relay durumu."""

    last_id: int = 0
    last_event_at: datetime | None = None
    lag_seconds: float | None = None
    relayed: int = 0


async def run_outbox_relay(
    repo: Repository,
    hub: WsHub,
    clock: Clock,
    state: RelayState,
    stop: asyncio.Event,
    *,
    poll_interval: float = 0.5,
) -> None:
    """Yeni outbox olaylarını WS konularına çevirip yayınlar. `stop` ile biter."""
    outbox = Outbox(repo, clock)
    state.last_id = await repo.outbox_max_id()
    async for event in outbox.tail(stop, poll_interval=poll_interval, start_after=state.last_id):
        now = clock.now()
        state.last_id = event.id
        state.last_event_at = now
        state.lag_seconds = max(0.0, (now - event.created_at).total_seconds())
        state.relayed += 1
        topic = ws_topic_for(event)
        try:
            await hub.broadcast(topic, event.payload, now)
        except Exception as exc:  # tek olayın hatası relay'i durdurmaz
            logger.warning("relay yayın hatası ({topic}): {err}", topic=topic, err=repr(exc))
