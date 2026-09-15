"""Tahmin defteri: her tahmin modül skorlarıyla birlikte tek transaction'da yazılır."""

from collections.abc import Sequence
from datetime import datetime

from marketpulse.core.clock import Clock
from marketpulse.core.time import EPOCH
from marketpulse.core.types import Horizon
from marketpulse.storage.models import NewPrediction, SignalRow
from marketpulse.storage.outbox import Outbox
from marketpulse.storage.repository import Repository


def is_non_overlapping(as_of: datetime, horizon: Horizon) -> bool:
    """Tahmin, ufuk uzunluğunun epoch ızgarasına oturuyor mu? (ARCHITECTURE.md §5)

    Örtüşmesiz alt küme metriklerde ayrıca hesaplanır; örtüşen tahminler metrikleri şişirebilir.
    """
    return (as_of - EPOCH) % horizon.length == (as_of - as_of)


class Ledger:
    """Tahmin yazma ve `prediction.created` olayını yayınlama."""

    def __init__(self, repo: Repository, clock: Clock, outbox: Outbox | None = None) -> None:
        self._repo = repo
        self._clock = clock
        self._outbox = outbox

    async def record(self, prediction: NewPrediction, signals: Sequence[SignalRow] = ()) -> int:
        prediction_id = await self._repo.write_prediction(
            prediction, signals, created_at=self._clock.now()
        )
        if self._outbox is not None:
            await self._outbox.emit(
                "prediction.created",
                {
                    "id": prediction_id,
                    "symbol": prediction.symbol,
                    "horizon": prediction.horizon.value,
                    "as_of": prediction.as_of,
                    "target_at": prediction.target_at,
                    "p_up": prediction.p_up,
                    "confidence": prediction.confidence,
                    "confidence_label": prediction.confidence_label,
                    "source": prediction.source,
                    "price_at": prediction.price_at,
                },
            )
        return prediction_id
