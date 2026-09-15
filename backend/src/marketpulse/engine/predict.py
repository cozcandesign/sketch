"""Tahmin işi (Faz 1: yalnızca referans tahminciler).

Faz 2'den itibaren gerçek sinyal modülleri ve ensemble buraya eklenir; referanslar kalıcıdır
çünkü her modülün yenmesi gereken taban çizgisidir (ARCHITECTURE.md §11.4).
"""

from collections.abc import Sequence
from datetime import datetime

from loguru import logger

from marketpulse.core.types import Horizon, Interval
from marketpulse.storage.models import NewPrediction
from marketpulse.storage.repository import Repository
from marketpulse.tracking import baselines
from marketpulse.tracking.ledger import Ledger, is_non_overlapping

PRICE_INTERVAL = Interval.M1  # K16: gerçek sonuç ve başlangıç fiyatı spot 1 dk kapanışından
BASELINE_CONFIDENCE = 0.2
P_MIN = 0.10
P_MAX = 0.90


def clip_probability(p_up: float) -> float:
    """K19: kalibrasyon kanıtlanana kadar olasılık [0.10, 0.90] aralığına kırpılır."""
    return min(P_MAX, max(P_MIN, p_up))


async def run_baseline_predictions(
    repo: Repository,
    ledger: Ledger,
    *,
    symbols: Sequence[str],
    horizon: Horizon,
    as_of: datetime,
) -> int:
    """Her sembol için iki referans tahmini yazar. Yazılan tahmin sayısını döner."""
    written = 0
    for symbol in symbols:
        candle = await repo.latest_candle(symbol, PRICE_INTERVAL, as_of=as_of)
        if candle is None:
            logger.bind(symbol=symbol, horizon=horizon.value).debug(
                "fiyat mumu yok, tahmin atlandı"
            )
            continue
        for result in (
            await baselines.climatology(repo, symbol, horizon, as_of),
            await baselines.momentum(repo, symbol, horizon, as_of),
        ):
            await ledger.record(
                NewPrediction(
                    symbol=symbol,
                    horizon=horizon,
                    as_of=as_of,
                    target_at=as_of + horizon.length,
                    price_at=candle.close,
                    p_up=clip_probability(result.p_up),
                    confidence=BASELINE_CONFIDENCE,
                    confidence_label="low",
                    ensemble_version=result.version,
                    non_overlapping=is_non_overlapping(as_of, horizon),
                    source="baseline",
                    report={
                        "headline": f"{symbol} · {horizon.label_tr} · referans tahmin",
                        "reasons": [{"module": "baseline", "text": result.note_tr}],
                        "samples": result.samples,
                    },
                )
            )
            written += 1
    return written
