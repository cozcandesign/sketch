"""`/market`: canlı fiyat, mum kapsamı ve ufuk bazlı son tahminler."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from marketpulse.api.deps import get_clock, get_repo, get_settings
from marketpulse.api.schemas.market import (
    CandleCoverageOut,
    CandleOut,
    CandlesOut,
    HorizonStateOut,
    MarketStateOut,
    PriceOut,
    SymbolsOut,
)
from marketpulse.api.schemas.predictions import PredictionOut
from marketpulse.config import Settings
from marketpulse.core.clock import Clock
from marketpulse.core.types import Horizon, Interval
from marketpulse.storage.repository import Repository

router = APIRouter(tags=["market"])

PRICE_INTERVAL = Interval.M1
PRICE_STALE_AFTER = timedelta(minutes=3)
COVERAGE_INTERVALS = (Interval.M1, Interval.M5, Interval.M15, Interval.H1, Interval.H4, Interval.D1)
MAX_CANDLES = 2000
PREDICTIONS_PER_HORIZON = 4


def _check_symbol(symbol: str, settings: Settings) -> str:
    normalized = symbol.upper()
    if normalized not in settings.symbols:
        raise HTTPException(status_code=404, detail=f"takip edilmeyen sembol: {symbol}")
    return normalized


@router.get("/symbols", response_model=SymbolsOut)
async def list_symbols(settings: Annotated[Settings, Depends(get_settings)]) -> SymbolsOut:
    return SymbolsOut(symbols=list(settings.symbols), timezone=settings.timezone)


@router.get("/market/{symbol}", response_model=MarketStateOut)
async def get_market(
    symbol: str,
    repo: Annotated[Repository, Depends(get_repo)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MarketStateOut:
    normalized = _check_symbol(symbol, settings)
    now = clock.now()
    latest = await repo.latest_candle(normalized, PRICE_INTERVAL)
    day_ago = await repo.get_candle_closing_at(
        normalized, PRICE_INTERVAL, (latest.close_time - timedelta(hours=24)) if latest else now
    )
    change = None
    if latest is not None and day_ago is not None and day_ago.close:
        change = latest.close / day_ago.close - 1.0

    coverage: list[CandleCoverageOut] = []
    for interval in COVERAGE_INTERVALS:
        newest = await repo.latest_candle(normalized, interval)
        coverage.append(
            CandleCoverageOut(
                interval=interval.value,
                count=await repo.count_candles(normalized, interval),
                last_close_time=newest.close_time if newest else None,
            )
        )

    horizons = []
    for horizon in Horizon:
        rows = await repo.list_predictions(
            symbol=normalized, horizon=horizon, limit=PREDICTIONS_PER_HORIZON
        )
        horizons.append(
            HorizonStateOut(
                horizon=horizon.value,
                label_tr=horizon.label_tr,
                predictions=[PredictionOut.from_row(p) for p in rows],
            )
        )

    return MarketStateOut(
        symbol=normalized,
        price=PriceOut(
            last=latest.close if latest else None,
            change_24h=change,
            as_of=latest.close_time if latest else None,
            stale=latest is None or (now - latest.close_time) > PRICE_STALE_AFTER,
        ),
        coverage=coverage,
        horizons=horizons,
    )


@router.get("/market/{symbol}/candles", response_model=CandlesOut)
async def get_candles(
    symbol: str,
    repo: Annotated[Repository, Depends(get_repo)],
    settings: Annotated[Settings, Depends(get_settings)],
    interval: Interval = Interval.M15,
    limit: Annotated[int, Query(ge=1, le=MAX_CANDLES)] = 500,
) -> CandlesOut:
    normalized = _check_symbol(symbol, settings)
    candles = await repo.get_candles(normalized, interval, limit=limit)
    return CandlesOut(
        symbol=normalized,
        interval=interval.value,
        candles=[
            CandleOut(
                time=int(c.open_time.timestamp()),
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in candles
        ],
    )
