"""Piyasa durumu ve mum uçlarının şemaları."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from marketpulse.api.schemas.predictions import PredictionOut


class PriceOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    last: float | None
    change_24h: float | None
    as_of: datetime | None
    stale: bool


class CandleCoverageOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval: str
    count: int
    last_close_time: datetime | None


class HorizonStateOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    horizon: str
    label_tr: str
    predictions: list[PredictionOut]


class MarketStateOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    price: PriceOut
    coverage: list[CandleCoverageOut]
    horizons: list[HorizonStateOut]


class CandleOut(BaseModel):
    """lightweight-charts biçimi: `time` saniye cinsinden UNIX zamanı (mum açılışı)."""

    model_config = ConfigDict(frozen=True)

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    interval: str
    candles: list[CandleOut]


class SymbolsOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbols: list[str]
    timezone: str
