"""`/predictions`: tahmin geçmişi ve tek tahmin ayrıntısı."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from marketpulse.api.deps import get_repo
from marketpulse.api.schemas.predictions import PredictionOut, PredictionPage
from marketpulse.core.types import Horizon
from marketpulse.storage.repository import Repository

router = APIRouter(tags=["predictions"])

MAX_LIMIT = 200


@router.get("/predictions", response_model=PredictionPage)
async def list_predictions(
    repo: Annotated[Repository, Depends(get_repo)],
    symbol: str | None = None,
    horizon: Horizon | None = None,
    source: Literal["live", "baseline", "backtest"] | None = None,
    status: Literal["active", "resolved", "all"] = "all",
    since: datetime | None = None,
    cursor: int | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 100,
) -> PredictionPage:
    resolved = {"active": False, "resolved": True, "all": None}[status]
    rows = await repo.list_predictions(
        symbol=symbol,
        horizon=horizon,
        source=source,
        resolved=resolved,
        since=since,
        cursor=cursor,
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return PredictionPage(
        items=[PredictionOut.from_row(p) for p in page],
        next_cursor=page[-1].id if has_more and page else None,
    )


@router.get("/predictions/{prediction_id}", response_model=PredictionOut)
async def get_prediction(
    prediction_id: int, repo: Annotated[Repository, Depends(get_repo)]
) -> PredictionOut:
    prediction = await repo.get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="tahmin bulunamadı")
    return PredictionOut.from_row(prediction)
