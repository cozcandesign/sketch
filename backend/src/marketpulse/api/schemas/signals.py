"""Sinyal ve seviye uçlarının yanıt şemaları."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from marketpulse.api.schemas.predictions import SignalOut
from marketpulse.storage.models import ConfidenceLabel


class HorizonSignalsOut(BaseModel):
    """Bir ufkun en son canlı tahmini ve o tahmini üreten modül skorları."""

    model_config = ConfigDict(frozen=True)

    horizon: str
    label_tr: str
    prediction_id: int | None
    as_of: datetime | None
    p_up: float | None
    combined_score: float | None
    confidence: float | None
    confidence_label: ConfidenceLabel | None
    conflict: bool
    veto_active: bool
    modules: list[SignalOut]
    report: dict[str, Any] | None


class SignalsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    horizons: list[HorizonSignalsOut]


class LevelOut(BaseModel):
    """Mekanik destek/direnç seviyesi."""

    model_config = ConfigDict(frozen=True)

    price: float
    kind: str  # "high" (direnç) | "low" (destek)
    touches: int
    distance_atr: float | None


class VolumeProfileOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    poc: float
    value_area_low: float
    value_area_high: float


class LevelsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    interval: str
    price: float | None
    atr: float | None
    levels: list[LevelOut]
    volume_profile: VolumeProfileOut | None
