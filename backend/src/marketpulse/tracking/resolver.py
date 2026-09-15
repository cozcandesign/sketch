"""Sonuç çözümleyici (ARCHITECTURE.md §11.1).

Ufku dolan her tahmin için gerçek sonucu yazar. Yalnızca `target_at` anında **kapanmış** spot
1 dakikalık mum kullanılır (K16, look-ahead kuralı 6).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.core.types import Interval
from marketpulse.storage.models import Prediction, PredictionOutcome
from marketpulse.storage.outbox import Outbox
from marketpulse.storage.repository import Repository

REST_GRACE = timedelta(minutes=10)
UNRESOLVED_AFTER = timedelta(hours=24)
RESOLVE_INTERVAL = Interval.M1


@dataclass(frozen=True)
class ResolveStats:
    resolved: int = 0
    unresolved: int = 0
    waiting: int = 0
    backfilled: int = 0


def outcome_for(
    prediction: Prediction, price_at_target: float, resolved_at: datetime, resolved_by: str
) -> PredictionOutcome:
    """Fiyattan sonuç, isabet ve Brier skorunu hesaplar.

    `outcome = 'up'` ancak hedef fiyat başlangıçtan **kesin** yüksekse; eşitlik `down` sayılır
    (nadir, dokümante edilmiştir). `hit = (p_up > 0.5) == (outcome == 'up')`.
    """
    went_up = price_at_target > prediction.price_at
    y = 1 if went_up else 0
    return PredictionOutcome(
        prediction_id=prediction.id,
        resolved_at=resolved_at,
        price_at_target=price_at_target,
        realized_return=price_at_target / prediction.price_at - 1.0,
        outcome="up" if went_up else "down",
        hit=(prediction.p_up > 0.5) == went_up,
        brier=(prediction.p_up - y) ** 2,
        resolved_by=resolved_by,
    )


class Resolver:
    """Ufku dolmuş tahminleri çözümler; mum gecikirse REST ile tamamlar."""

    def __init__(
        self,
        repo: Repository,
        clock: Clock,
        outbox: Outbox | None = None,
        *,
        backfill: object | None = None,
        rest_grace: timedelta = REST_GRACE,
        unresolved_after: timedelta = UNRESOLVED_AFTER,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._outbox = outbox
        self._backfill = backfill
        self._rest_grace = rest_grace
        self._unresolved_after = unresolved_after

    async def resolve_due(self) -> ResolveStats:
        now = self._clock.now()
        resolved = unresolved = waiting = backfilled = 0
        for prediction in await self._repo.due_predictions(now):
            candle = await self._repo.get_candle_closing_at(
                prediction.symbol, RESOLVE_INTERVAL, prediction.target_at
            )
            source = "ws"
            if candle is None and now >= prediction.target_at + self._rest_grace:
                if await self._try_backfill(prediction):
                    backfilled += 1
                candle = await self._repo.get_candle_closing_at(
                    prediction.symbol, RESOLVE_INTERVAL, prediction.target_at
                )
                source = "rest_backfill"
            if candle is not None:
                await self._write(outcome_for(prediction, candle.close, now, source))
                resolved += 1
            elif now >= prediction.target_at + self._unresolved_after:
                await self._write(
                    PredictionOutcome(
                        prediction_id=prediction.id,
                        resolved_at=now,
                        price_at_target=None,
                        realized_return=None,
                        outcome="unresolved",
                        hit=None,
                        brier=None,
                        resolved_by="rest_backfill",
                    )
                )
                unresolved += 1
                logger.bind(symbol=prediction.symbol, horizon=prediction.horizon.value).warning(
                    "tahmin çözümlenemedi: {at} mumu yok", at=prediction.target_at.isoformat()
                )
            else:
                waiting += 1
        return ResolveStats(
            resolved=resolved, unresolved=unresolved, waiting=waiting, backfilled=backfilled
        )

    async def _try_backfill(self, prediction: Prediction) -> bool:
        """Eksik mumu REST ile çekmeyi dener. Backfill sağlayıcısı yoksa sessizce geçer."""
        fetch = getattr(self._backfill, "fetch_candle", None)
        if fetch is None:
            return False
        try:
            await fetch(prediction.symbol, RESOLVE_INTERVAL, prediction.target_at)
        except Exception as exc:  # çözümleme, collector hatası yüzünden durmaz
            logger.warning("resolver REST doldurma hatası: {err}", err=repr(exc))
            return False
        return True

    async def _write(self, outcome: PredictionOutcome) -> None:
        await self._repo.write_outcome(outcome)
        if self._outbox is not None:
            await self._outbox.emit(
                "outcome.resolved",
                {
                    "prediction_id": outcome.prediction_id,
                    "outcome": outcome.outcome,
                    "hit": outcome.hit,
                    "brier": outcome.brier,
                    "realized_return": outcome.realized_return,
                },
            )
