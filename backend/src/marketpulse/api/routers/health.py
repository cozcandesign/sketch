"""`GET /api/v1/health`: collector sağlığı, engine heartbeat, DB boyutu, relay ve WS durumu."""

from typing import Annotated

from fastapi import APIRouter, Depends

from marketpulse import __version__
from marketpulse.api.deps import get_clock, get_hub, get_relay_state, get_repo, get_settings
from marketpulse.api.outbox_relay import RelayState
from marketpulse.api.schemas.health import (
    CollectorHealthOut,
    DbHealthOut,
    EngineHealthOut,
    HealthResponse,
    OutboxHealthOut,
    WsHealthOut,
)
from marketpulse.api.ws import WsHub
from marketpulse.config import Settings
from marketpulse.core.clock import Clock
from marketpulse.storage.repository import Repository

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(
    repo: Annotated[Repository, Depends(get_repo)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
    hub: Annotated[WsHub, Depends(get_hub)],
    relay: Annotated[RelayState, Depends(get_relay_state)],
) -> HealthResponse:
    now = clock.now()
    heartbeat = await repo.read_heartbeat()
    age = (now - heartbeat.ts).total_seconds() if heartbeat else None
    alive = age is not None and age < settings.heartbeat_stale_after_sec
    collectors = [CollectorHealthOut(**c.model_dump()) for c in await repo.list_collector_health()]

    if not alive:
        overall = "down"
    elif any(c.status in {"degraded", "down"} for c in collectors):
        overall = "degraded"
    else:
        overall = "ok"

    return HealthResponse(
        status=overall,
        server_time=now,
        api_version=__version__,
        engine=EngineHealthOut(
            alive=alive,
            last_heartbeat=heartbeat.ts if heartbeat else None,
            age_seconds=age,
            version=heartbeat.version if heartbeat else None,
        ),
        collectors=collectors,
        db=DbHealthOut(size_bytes=await repo.db_size_bytes()),
        outbox=OutboxHealthOut(
            last_id=relay.last_id, last_event_at=relay.last_event_at, lag_seconds=relay.lag_seconds
        ),
        ws=WsHealthOut(clients=hub.client_count),
    )
