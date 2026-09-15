"""Kalibrasyon (doğruluk) uçlarının şemaları."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class SummaryOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    n: int
    brier: float | None
    brier_skill: float | None
    base_rate: float | None
    hit_rate: float | None
    hit_ci_low: float | None
    hit_ci_high: float | None
    beats_uninformed: bool


class ModelSummaryOut(SummaryOut):
    model_version: str
    label_tr: str


class HorizonSummaryOut(SummaryOut):
    horizon: str
    label_tr: str


class CalibrationBinOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    bin: int
    lower: float
    upper: float
    n: int
    mean_p: float | None
    observed_freq: float | None


class DailyPointOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    day: date
    n: int
    brier: float
    hit_rate: float


class CalibrationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    subset: str
    window_days: int | None
    overall: SummaryOut
    by_model: list[ModelSummaryOut]
    by_horizon: list[HorizonSummaryOut]
    bins: list[CalibrationBinOut]
    daily: list[DailyPointOut]
    pending: int
