"""`GET /api/v1/health` yanıt şeması. Veri durumu şeridi bunu okur (ARCHITECTURE.md §15)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from marketpulse.storage.models import HealthStatus


class CollectorHealthOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    collector: str
    status: HealthStatus
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None
    consecutive_failures: int


class EngineHealthOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    alive: bool
    last_heartbeat: datetime | None
    age_seconds: float | None
    version: str | None


class DbHealthOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    size_bytes: int | None


class OutboxHealthOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    last_id: int
    last_event_at: datetime | None
    lag_seconds: float | None


class WsHealthOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    clients: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded", "down"]
    server_time: datetime
    api_version: str
    engine: EngineHealthOut
    collectors: list[CollectorHealthOut]
    db: DbHealthOut
    outbox: OutboxHealthOut
    ws: WsHealthOut
