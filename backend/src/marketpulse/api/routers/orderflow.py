"""`/market/{symbol}/orderflow`: türev piyasa panelinin verisi.

Api okuyucudur: burada yalnızca yazılmış satırlar okunur ve panel için düzenlenir. Kümülatif CVD
pencerenin başından itibaren toplanır — mutlak bir CVD değeri yoktur, ancak pencere içindeki
değişimi anlamlıdır.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from marketpulse.api.deps import get_clock, get_repo, get_settings
from marketpulse.api.derivatives import (
    FUNDING_WINDOW,
    OI_WINDOW,
    average_rate,
    coverage_ratio,
    funding_zscore,
    open_interest_summary,
)
from marketpulse.api.schemas.signals import (
    FundingOut,
    LiquidationOut,
    LongShortOut,
    OrderflowOut,
    OrderflowPointOut,
)
from marketpulse.config import Settings
from marketpulse.core.clock import Clock
from marketpulse.storage.models import LongShortPoint, OrderflowRow
from marketpulse.storage.repository import Repository

router = APIRouter(tags=["orderflow"])

DEFAULT_MINUTES = 240
MAX_MINUTES = 1440
LIQUIDATION_LIMIT = 200


def _check_symbol(symbol: str, settings: Settings) -> str:
    normalized = symbol.upper()
    if normalized not in settings.symbols:
        raise HTTPException(status_code=404, detail=f"takip edilmeyen sembol: {symbol}")
    return normalized


@router.get("/market/{symbol}/orderflow", response_model=OrderflowOut)
async def get_orderflow(
    symbol: str,
    repo: Annotated[Repository, Depends(get_repo)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
    minutes: Annotated[int, Query(ge=5, le=MAX_MINUTES)] = DEFAULT_MINUTES,
) -> OrderflowOut:
    normalized = _check_symbol(symbol, settings)
    now = clock.now()
    since = now - timedelta(minutes=minutes)

    flow = await repo.get_orderflow(normalized, start=since)
    liquidations = await repo.get_liquidations(normalized, start=since)
    funding_history = await repo.get_funding_rates(normalized, start=now - FUNDING_WINDOW)
    funding_live = await repo.get_funding_live(normalized, start=now - timedelta(hours=2))
    open_interest = await repo.get_open_interest(normalized, start=now - OI_WINDOW)
    long_short = await repo.get_long_short(normalized, start=now - timedelta(hours=1))

    live = funding_live[-1] if funding_live else None
    last_rate = live.last_rate if live else (funding_history[-1].rate if funding_history else None)
    return OrderflowOut(
        symbol=normalized,
        minutes=_points(flow),
        liquidations=[
            LiquidationOut(ts=row.ts, side=row.side, qty=row.qty, price=row.price, usd=row.usd)
            for row in liquidations[-LIQUIDATION_LIMIT:]
        ],
        funding=FundingOut(
            last_rate=last_rate,
            next_funding_time=live.next_funding_time if live else None,
            mark_price=live.mark_price if live else None,
            average_30d=average_rate(funding_history),
            zscore=funding_zscore(last_rate, funding_history),
        ),
        open_interest=open_interest_summary(open_interest),
        long_short=_latest_long_short(long_short),
        coverage_ratio=coverage_ratio(flow, minutes),
    )


def _points(flow: list[OrderflowRow]) -> list[OrderflowPointOut]:
    """Dakika satırları + kümülatif CVD (pencere başından itibaren)."""
    cumulative = 0.0
    points: list[OrderflowPointOut] = []
    for row in flow:
        cumulative += row.cvd_delta or 0.0
        points.append(
            OrderflowPointOut(
                ts=row.ts,
                buy_vol=row.buy_vol,
                sell_vol=row.sell_vol,
                cvd_delta=row.cvd_delta,
                cvd_cumulative=round(cumulative, 6),
                trade_count=row.trade_count,
                liq_long_usd=row.liq_long_usd,
                liq_short_usd=row.liq_short_usd,
                top20_imbalance=row.top20_imbalance,
                depth1pct_imbalance=row.depth1pct_imbalance,
                spread_bps=row.spread_bps,
                coverage_seconds=row.coverage_seconds,
            )
        )
    return points


def _latest_long_short(rows: list[LongShortPoint]) -> list[LongShortOut]:
    """Her tür için yalnızca en son satır (panelde üç oran gösterilir)."""
    latest: dict[str, LongShortOut] = {}
    for row in rows:
        latest[row.kind] = LongShortOut(
            kind=row.kind,
            long_ratio=row.long_ratio,
            short_ratio=row.short_ratio,
            ratio=row.ratio,
            ts=row.ts,
        )
    return [latest[kind] for kind in sorted(latest)]
