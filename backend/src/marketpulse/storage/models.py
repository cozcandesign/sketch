"""Repository'nin döndürdüğü küçük veri modelleri (Faz 0 kapsamı)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

HealthStatus = Literal["ok", "degraded", "down", "disabled", "budget_exhausted"]


class Heartbeat(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts: datetime
    version: str


class CollectorHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    collector: str
    status: HealthStatus
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0


class OutboxEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    created_at: datetime
    topic: str
    payload: dict[str, Any]
