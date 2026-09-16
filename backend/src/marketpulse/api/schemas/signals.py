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


class OrderflowPointOut(BaseModel):
    """Bir dakikalık order flow özeti (panel grafikleri için)."""

    model_config = ConfigDict(frozen=True)

    ts: datetime
    buy_vol: float | None
    sell_vol: float | None
    cvd_delta: float | None
    cvd_cumulative: float
    trade_count: int | None
    liq_long_usd: float | None
    liq_short_usd: float | None
    top20_imbalance: float | None
    depth1pct_imbalance: float | None
    spread_bps: float | None
    coverage_seconds: float | None


class LiquidationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    ts: datetime
    side: str  # long | short
    qty: float
    price: float
    usd: float


class FundingOut(BaseModel):
    """Anlık funding durumu ve son gerçekleşen ödemeler."""

    model_config = ConfigDict(frozen=True)

    last_rate: float | None
    next_funding_time: datetime | None
    mark_price: float | None
    average_30d: float | None
    zscore: float | None


class OpenInterestOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    latest: float | None
    ts: datetime | None
    change_24h: float | None  # oransal değişim


class LongShortOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    long_ratio: float
    short_ratio: float
    ratio: float
    ts: datetime


class OrderflowOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    minutes: list[OrderflowPointOut]
    liquidations: list[LiquidationOut]
    funding: FundingOut
    open_interest: OpenInterestOut
    long_short: list[LongShortOut]
    coverage_ratio: float  # penceredeki dakikaların dinlenmiş oranı (0..1)
