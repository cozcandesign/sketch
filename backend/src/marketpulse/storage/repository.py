"""Depolama arayüzü. SQL yalnızca `storage/` içinde yazılır; diğer paketler bu protokolü kullanır.

TimescaleDB geçişi yeni bir implementasyonla yapılır (ARCHITECTURE.md §20).
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol

from marketpulse.core.types import Horizon, Interval
from marketpulse.storage.models import (
    Candle,
    CandleGap,
    CollectorHealth,
    FundingLive,
    FundingRate,
    Heartbeat,
    Liquidation,
    LongShortPoint,
    ModuleResolvedRow,
    NewPrediction,
    OpenInterestPoint,
    OrderflowRow,
    OutboxEvent,
    Prediction,
    PredictionOutcome,
    ResolvedRow,
    SignalRow,
    TakerVolumePoint,
)


class Repository(Protocol):
    async def create_all(self) -> None: ...
    async def close(self) -> None: ...

    # --- engine heartbeat ---
    async def write_heartbeat(self, ts: datetime, version: str) -> None: ...
    async def read_heartbeat(self) -> Heartbeat | None: ...
    async def clear_heartbeat(self) -> None: ...

    # --- collector sağlığı ---
    async def upsert_collector_health(self, health: CollectorHealth) -> None: ...
    async def upsert_collector_health_many(self, rows: Sequence[CollectorHealth]) -> None: ...
    async def list_collector_health(self) -> list[CollectorHealth]: ...

    # --- outbox ---
    async def outbox_emit(
        self, topic: str, payload: dict[str, Any], created_at: datetime
    ) -> int: ...
    async def outbox_read_after(self, last_id: int, limit: int = 500) -> list[OutboxEvent]: ...
    async def outbox_max_id(self) -> int: ...
    async def outbox_prune(self, before: datetime) -> int: ...

    # --- ayarlar ---
    async def get_setting(self, key: str) -> Any | None: ...
    async def set_setting(self, key: str, value: Any, updated_at: datetime) -> None: ...

    # --- mumlar ---
    async def upsert_candles(self, candles: Sequence[Candle]) -> int: ...
    async def get_candles(
        self,
        symbol: str,
        interval: Interval,
        *,
        as_of: datetime | None = None,
        start: datetime | None = None,
        limit: int | None = None,
    ) -> list[Candle]: ...
    async def get_candle_closing_at(
        self, symbol: str, interval: Interval, close_time: datetime
    ) -> Candle | None: ...
    async def latest_candle(
        self, symbol: str, interval: Interval, *, as_of: datetime | None = None
    ) -> Candle | None: ...
    async def count_candles(self, symbol: str, interval: Interval) -> int: ...
    async def find_candle_gaps(
        self, symbol: str, interval: Interval, *, since: datetime, until: datetime
    ) -> list[CandleGap]: ...
    async def delete_candles_before(self, interval: Interval, before: datetime) -> int: ...

    # --- tahmin defteri ---
    async def write_prediction(
        self, prediction: NewPrediction, signals: Sequence[SignalRow] = (), *, created_at: datetime
    ) -> int: ...
    async def get_prediction(self, prediction_id: int) -> Prediction | None: ...
    async def list_predictions(
        self,
        *,
        symbol: str | None = None,
        horizon: Horizon | None = None,
        source: str | None = None,
        resolved: bool | None = None,
        since: datetime | None = None,
        cursor: int | None = None,
        limit: int = 100,
    ) -> list[Prediction]: ...
    async def due_predictions(self, now: datetime, *, limit: int = 500) -> list[Prediction]: ...
    async def write_outcome(self, outcome: PredictionOutcome) -> None: ...
    async def resolved_rows(
        self,
        *,
        symbol: str | None = None,
        horizon: Horizon | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> list[ResolvedRow]: ...

    async def resolved_module_rows(
        self,
        *,
        symbol: str | None = None,
        horizon: Horizon | None = None,
        since: datetime | None = None,
    ) -> list[ModuleResolvedRow]: ...

    # --- türev piyasa ---
    async def upsert_funding_rates(self, rows: Sequence[FundingRate]) -> int: ...
    async def upsert_funding_live(self, rows: Sequence[FundingLive]) -> int: ...
    async def upsert_open_interest(self, rows: Sequence[OpenInterestPoint]) -> int: ...
    async def upsert_long_short(self, rows: Sequence[LongShortPoint]) -> int: ...
    async def upsert_taker_volume(self, rows: Sequence[TakerVolumePoint]) -> int: ...
    async def upsert_orderflow(self, rows: Sequence[OrderflowRow]) -> int: ...
    async def insert_liquidations(self, rows: Sequence[Liquidation]) -> int: ...
    async def get_orderflow(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[OrderflowRow]: ...
    async def get_liquidations(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[Liquidation]: ...
    async def get_funding_rates(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[FundingRate]: ...
    async def get_funding_live(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[FundingLive]: ...
    async def get_open_interest(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[OpenInterestPoint]: ...
    async def get_long_short(
        self,
        symbol: str,
        *,
        kind: str | None = None,
        as_of: datetime | None = None,
        start: datetime | None = None,
    ) -> list[LongShortPoint]: ...
    async def get_taker_volume(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[TakerVolumePoint]: ...

    # --- ağırlıklar ---
    async def get_weights(self, horizon: Horizon) -> dict[str, float]: ...
    async def count_weights(self) -> int: ...
    async def seed_weights(
        self,
        table: Mapping[Horizon, Mapping[str, float]],
        *,
        valid_from: datetime,
        source: str = "default",
    ) -> int: ...

    # --- meta ---
    async def db_size_bytes(self) -> int | None: ...
