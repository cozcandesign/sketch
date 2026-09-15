"""Tahmin defteri, sonuçlar ve metrik tabloları."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Row, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from marketpulse.core.types import Horizon
from marketpulse.storage import tables as t
from marketpulse.storage.models import (
    NewPrediction,
    Prediction,
    PredictionOutcome,
    ResolvedRow,
    SignalRow,
)
from marketpulse.storage.sqlite_base import SqliteBase, dump_json, load_json


def _prediction_from_row(
    row: dict[str, Any], outcome: PredictionOutcome | None = None
) -> Prediction:
    return Prediction(
        id=row["id"],
        created_at=row["created_at"],
        symbol=row["symbol"],
        horizon=Horizon(row["horizon"]),
        as_of=row["as_of"],
        target_at=row["target_at"],
        price_at=row["price_at"],
        p_up=row["p_up"],
        expected_low=row["expected_low"],
        expected_high=row["expected_high"],
        confidence=row["confidence"],
        confidence_label=row["confidence_label"],
        conflict=bool(row["conflict"]),
        veto_active=bool(row["veto_active"]),
        veto_reason=row["veto_reason"],
        combined_score=row["combined_score"],
        weights=load_json(row["weights_json"]),
        ensemble_version=row["ensemble_version"],
        non_overlapping=bool(row["non_overlapping"]),
        source=row["source"],
        run_id=row["run_id"],
        report=load_json(row["report_json"]),
        outcome=outcome,
    )


def _outcome_from_row(row: dict[str, Any]) -> PredictionOutcome | None:
    if row.get("resolved_at") is None:
        return None
    return PredictionOutcome(
        prediction_id=row["prediction_id"],
        resolved_at=row["resolved_at"],
        price_at_target=row["price_at_target"],
        realized_return=row["realized_return"],
        outcome=row["outcome"],
        hit=None if row["hit"] is None else bool(row["hit"]),
        brier=row["brier"],
        resolved_by=row["resolved_by"],
    )


class LedgerMixin(SqliteBase):
    async def write_prediction(
        self, prediction: NewPrediction, signals: Sequence[SignalRow] = (), *, created_at: datetime
    ) -> int:
        """Tahmini ve modül skorlarını **tek transaction**'da yazar; tahmin id'sini döner."""
        values = {
            "symbol": prediction.symbol,
            "horizon": prediction.horizon.value,
            "as_of": prediction.as_of,
            "target_at": prediction.target_at,
            "created_at": created_at,
            "price_at": prediction.price_at,
            "p_up": prediction.p_up,
            "expected_low": prediction.expected_low,
            "expected_high": prediction.expected_high,
            "confidence": prediction.confidence,
            "confidence_label": prediction.confidence_label,
            "conflict": prediction.conflict,
            "veto_active": prediction.veto_active,
            "veto_reason": prediction.veto_reason,
            "combined_score": prediction.combined_score,
            "weights_json": None if prediction.weights is None else dump_json(prediction.weights),
            "ensemble_version": prediction.ensemble_version,
            "non_overlapping": prediction.non_overlapping,
            "source": prediction.source,
            "run_id": prediction.run_id,
            "report_json": None if prediction.report is None else dump_json(prediction.report),
        }
        async with self._engine.begin() as conn:
            result = await conn.execute(t.predictions.insert().values(**values))
            pk = result.inserted_primary_key
            if pk is None:
                msg = "prediction insert birincil anahtar döndürmedi"
                raise RuntimeError(msg)
            prediction_id = int(pk[0])
            if signals:
                await conn.execute(
                    t.prediction_signals.insert(),
                    [
                        {
                            "prediction_id": prediction_id,
                            "module": s.module,
                            "score": s.score,
                            "confidence": s.confidence,
                            "coverage": s.coverage,
                            "components_json": None
                            if s.components is None
                            else dump_json(s.components),
                            "rationale_json": None
                            if s.rationale is None
                            else dump_json(s.rationale),
                            "data_as_of": s.data_as_of,
                        }
                        for s in signals
                    ],
                )
        return prediction_id

    async def get_prediction(self, prediction_id: int) -> Prediction | None:
        join = t.predictions.outerjoin(
            t.prediction_outcomes, t.predictions.c.id == t.prediction_outcomes.c.prediction_id
        )
        stmt = (
            select(t.predictions, t.prediction_outcomes)
            .select_from(join)
            .where(t.predictions.c.id == prediction_id)
        )
        async with self._engine.connect() as conn:
            row = (await conn.execute(stmt)).mappings().first()
            if row is None:
                return None
            signal_rows = (
                (
                    await conn.execute(
                        select(t.prediction_signals)
                        .where(t.prediction_signals.c.prediction_id == prediction_id)
                        .order_by(t.prediction_signals.c.module)
                    )
                )
                .mappings()
                .all()
            )
        data = dict(row)
        prediction = _prediction_from_row(data, _outcome_from_row(data))
        signals = [
            SignalRow(
                module=s["module"],
                score=s["score"],
                confidence=s["confidence"],
                coverage=s["coverage"],
                components=load_json(s["components_json"]),
                rationale=load_json(s["rationale_json"]),
                data_as_of=s["data_as_of"],
            )
            for s in signal_rows
        ]
        return prediction.model_copy(update={"signals": signals})

    async def list_predictions(
        self,
        *,
        symbol: str | None = None,
        horizon: Horizon | None = None,
        source: str | None = None,
        resolved: bool | None = None,
        since: datetime | None = None,
        cursor: int | None = None,
        limit: int = 100,
    ) -> list[Prediction]:
        """En yeniden eskiye tahminler. `cursor` = son görülen id (ondan küçükler döner)."""
        join = t.predictions.outerjoin(
            t.prediction_outcomes, t.predictions.c.id == t.prediction_outcomes.c.prediction_id
        )
        conditions: list[ColumnElement[bool]] = []
        if symbol is not None:
            conditions.append(t.predictions.c.symbol == symbol)
        if horizon is not None:
            conditions.append(t.predictions.c.horizon == horizon.value)
        if source is not None:
            conditions.append(t.predictions.c.source == source)
        if since is not None:
            conditions.append(t.predictions.c.as_of >= since)
        if cursor is not None:
            conditions.append(t.predictions.c.id < cursor)
        if resolved is True:
            conditions.append(t.prediction_outcomes.c.prediction_id.is_not(None))
        elif resolved is False:
            conditions.append(t.prediction_outcomes.c.prediction_id.is_(None))
        stmt = (
            select(t.predictions, t.prediction_outcomes)
            .select_from(join)
            .where(*conditions)
            .order_by(t.predictions.c.id.desc())
            .limit(limit)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [_prediction_from_row(dict(r), _outcome_from_row(dict(r))) for r in rows]

    async def due_predictions(self, now: datetime, *, limit: int = 500) -> list[Prediction]:
        """Ufku dolmuş ve sonucu yazılmamış tahminler."""
        join = t.predictions.outerjoin(
            t.prediction_outcomes, t.predictions.c.id == t.prediction_outcomes.c.prediction_id
        )
        stmt = (
            select(t.predictions)
            .select_from(join)
            .where(
                t.predictions.c.target_at <= now,
                t.prediction_outcomes.c.prediction_id.is_(None),
            )
            .order_by(t.predictions.c.target_at)
            .limit(limit)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [_prediction_from_row(dict(r)) for r in rows]

    async def write_outcome(self, outcome: PredictionOutcome) -> None:
        stmt = sqlite_insert(t.prediction_outcomes).values(**outcome.model_dump())
        stmt = stmt.on_conflict_do_nothing(index_elements=[t.prediction_outcomes.c.prediction_id])
        async with self._engine.begin() as conn:
            await conn.execute(stmt)

    async def resolved_rows(
        self,
        *,
        symbol: str | None = None,
        horizon: Horizon | None = None,
        source: str | None = None,
        since: datetime | None = None,
    ) -> list[ResolvedRow]:
        """Metrik hesabı için çözümlenmiş tahminler (`unresolved` hariç)."""
        join = t.predictions.join(
            t.prediction_outcomes, t.predictions.c.id == t.prediction_outcomes.c.prediction_id
        )
        conditions: list[ColumnElement[bool]] = [
            t.prediction_outcomes.c.outcome.in_(("up", "down"))
        ]
        if symbol is not None:
            conditions.append(t.predictions.c.symbol == symbol)
        if horizon is not None:
            conditions.append(t.predictions.c.horizon == horizon.value)
        if source is not None:
            conditions.append(t.predictions.c.source == source)
        if since is not None:
            conditions.append(t.predictions.c.as_of >= since)
        stmt = (
            select(
                t.predictions.c.symbol,
                t.predictions.c.horizon,
                t.predictions.c.as_of,
                t.predictions.c.source,
                t.predictions.c.ensemble_version,
                t.predictions.c.p_up,
                t.predictions.c.non_overlapping,
                t.predictions.c.confidence_label,
                t.prediction_outcomes.c.outcome,
                t.prediction_outcomes.c.brier,
                t.prediction_outcomes.c.hit,
            )
            .select_from(join)
            .where(*conditions)
            .order_by(t.predictions.c.as_of)
        )
        async with self._engine.connect() as conn:
            rows: Sequence[Row[Any]] = (await conn.execute(stmt)).all()
        return [
            ResolvedRow(
                symbol=r.symbol,
                horizon=Horizon(r.horizon),
                as_of=r.as_of,
                source=r.source,
                ensemble_version=r.ensemble_version,
                p_up=r.p_up,
                y=1 if r.outcome == "up" else 0,
                brier=r.brier,
                hit=bool(r.hit),
                non_overlapping=bool(r.non_overlapping),
                confidence_label=r.confidence_label,
            )
            for r in rows
        ]
