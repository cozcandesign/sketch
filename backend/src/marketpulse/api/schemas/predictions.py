"""Tahmin uçlarının yanıt şemaları."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from marketpulse.storage.models import (
    ConfidenceLabel,
    OutcomeLabel,
    Prediction,
    PredictionSource,
)


class OutcomeOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    resolved_at: datetime
    price_at_target: float | None
    realized_return: float | None
    outcome: OutcomeLabel
    hit: bool | None
    brier: float | None
    resolved_by: str


class SignalOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    module: str
    score: float
    confidence: float
    coverage: float
    components: dict[str, float] | None
    rationale: list[str] | None


class PredictionOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    symbol: str
    horizon: str
    as_of: datetime
    target_at: datetime
    price_at: float
    p_up: float
    expected_low: float | None
    expected_high: float | None
    confidence: float
    confidence_label: ConfidenceLabel
    conflict: bool
    veto_active: bool
    veto_reason: str | None
    source: PredictionSource
    model_version: str
    non_overlapping: bool
    report: dict[str, Any] | None
    outcome: OutcomeOut | None
    signals: list[SignalOut] | None = None

    @classmethod
    def from_row(cls, prediction: Prediction) -> "PredictionOut":
        return cls(
            id=prediction.id,
            symbol=prediction.symbol,
            horizon=prediction.horizon.value,
            as_of=prediction.as_of,
            target_at=prediction.target_at,
            price_at=prediction.price_at,
            p_up=prediction.p_up,
            expected_low=prediction.expected_low,
            expected_high=prediction.expected_high,
            confidence=prediction.confidence,
            confidence_label=prediction.confidence_label,
            conflict=prediction.conflict,
            veto_active=prediction.veto_active,
            veto_reason=prediction.veto_reason,
            source=prediction.source,
            model_version=prediction.ensemble_version,
            non_overlapping=prediction.non_overlapping,
            report=prediction.report,
            outcome=None
            if prediction.outcome is None
            else OutcomeOut(**prediction.outcome.model_dump(exclude={"prediction_id"})),
            signals=None
            if prediction.signals is None
            else [
                SignalOut(
                    module=s.module,
                    score=s.score,
                    confidence=s.confidence,
                    coverage=s.coverage,
                    components=s.components,
                    rationale=s.rationale,
                )
                for s in prediction.signals
            ],
        )


class PredictionPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[PredictionOut]
    next_cursor: int | None
