"""`/signals` ve `/market/{symbol}/levels`: modül kırılımı ve mekanik fiyat seviyeleri.

Api süreci **okuyucudur**: modül skorları yeniden hesaplanmaz, engine'in tahminle birlikte yazdığı
`prediction_signals` satırları okunur. Böylece arayüzde görünen skor, o tahmini gerçekten üreten
skordur (yeniden hesap, aradan geçen zamanla farklı sonuç verirdi).

Seviyeler bunun istisnasıdır: yazılmış bir tahmine bağlı değildirler, o anki mumlardan türetilir ve
salt okunur hesaplanır (grafik üstü çizim için).
"""

from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from marketpulse.api.deps import get_repo, get_settings
from marketpulse.api.schemas.predictions import SignalOut
from marketpulse.api.schemas.signals import (
    HorizonSignalsOut,
    LevelOut,
    LevelsOut,
    SignalsOut,
    VolumeProfileOut,
)
from marketpulse.config import Settings
from marketpulse.core.types import Horizon, Interval
from marketpulse.features import indicators as ind
from marketpulse.features import levels as lv
from marketpulse.features.feature_store import candles_to_frame
from marketpulse.storage.models import Prediction
from marketpulse.storage.repository import Repository

router = APIRouter(tags=["signals"])

LEVELS_LOOKBACK = 400  # swing taraması için yeterli, sorgu hâlâ hızlı
ATR_PERIOD = 14
NEAR_ATR = 3.0  # fiyattan 3 ATR'den uzak seviyeler grafikte gürültüdür


def _check_symbol(symbol: str, settings: Settings) -> str:
    normalized = symbol.upper()
    if normalized not in settings.symbols:
        raise HTTPException(status_code=404, detail=f"takip edilmeyen sembol: {symbol}")
    return normalized


@router.get("/signals/{symbol}", response_model=SignalsOut)
async def get_signals(
    symbol: str,
    repo: Annotated[Repository, Depends(get_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SignalsOut:
    """Her ufuk için en son canlı tahmin ve onu üreten modül skorları."""
    normalized = _check_symbol(symbol, settings)
    horizons: list[HorizonSignalsOut] = []
    for horizon in Horizon:
        rows = await repo.list_predictions(
            symbol=normalized, horizon=horizon, source="live", limit=1
        )
        full = await repo.get_prediction(rows[0].id) if rows else None
        horizons.append(_horizon_signals(horizon, full))
    return SignalsOut(symbol=normalized, horizons=horizons)


def _horizon_signals(horizon: Horizon, prediction: Prediction | None) -> HorizonSignalsOut:
    if prediction is None:
        return HorizonSignalsOut(
            horizon=horizon.value,
            label_tr=horizon.label_tr,
            prediction_id=None,
            as_of=None,
            p_up=None,
            combined_score=None,
            confidence=None,
            confidence_label=None,
            conflict=False,
            veto_active=False,
            modules=[],
            report=None,
        )
    return HorizonSignalsOut(
        horizon=horizon.value,
        label_tr=horizon.label_tr,
        prediction_id=prediction.id,
        as_of=prediction.as_of,
        p_up=prediction.p_up,
        combined_score=prediction.combined_score,
        confidence=prediction.confidence,
        confidence_label=prediction.confidence_label,
        conflict=prediction.conflict,
        veto_active=prediction.veto_active,
        modules=[
            SignalOut(
                module=row.module,
                score=row.score,
                confidence=row.confidence,
                coverage=row.coverage,
                components=row.components,
                rationale=row.rationale,
            )
            for row in (prediction.signals or [])
        ],
        report=prediction.report,
    )


@router.get("/market/{symbol}/levels", response_model=LevelsOut)
async def get_levels(
    symbol: str,
    repo: Annotated[Repository, Depends(get_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
    interval: Interval = Interval.M15,
) -> LevelsOut:
    """Onaylanmış swing'lerden kümelenmiş destek/direnç ve hacim profili."""
    normalized = _check_symbol(symbol, settings)
    candles = await repo.get_candles(normalized, interval, limit=LEVELS_LOOKBACK)
    frame = candles_to_frame(candles)
    if frame.empty:
        return LevelsOut(
            symbol=normalized,
            interval=interval.value,
            price=None,
            atr=None,
            levels=[],
            volume_profile=None,
        )
    price = float(frame["close"].iloc[-1])
    atr_series = ind.atr(frame, ATR_PERIOD).dropna()
    atr_value = float(atr_series.iloc[-1]) if not atr_series.empty else None
    return LevelsOut(
        symbol=normalized,
        interval=interval.value,
        price=price,
        atr=atr_value,
        levels=_levels(frame, price, atr_value),
        volume_profile=_profile(frame),
    )


def _levels(frame: pd.DataFrame, price: float, atr_value: float | None) -> list[LevelOut]:
    if atr_value is None or atr_value <= 0:
        return []
    points = lv.swing_points(frame)
    clustered = lv.cluster_levels(points, tolerance=0.5 * atr_value)
    out: list[LevelOut] = []
    for level in clustered:
        distance = abs(level.price - price) / atr_value
        if distance > NEAR_ATR:
            continue
        out.append(
            LevelOut(
                price=level.price,
                kind=level.kind,
                touches=level.touches,
                distance_atr=round(distance, 2),
            )
        )
    return out


def _profile(frame: pd.DataFrame) -> VolumeProfileOut | None:
    profile = lv.volume_profile(frame)
    if profile is None:
        return None
    return VolumeProfileOut(
        poc=profile.poc,
        value_area_low=profile.value_area_low,
        value_area_high=profile.value_area_high,
    )
