"""Mum (kline) okuma/yazma. Look-ahead kuralı: sorgular `close_time <= as_of` ile kesilir."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import RowMapping

from marketpulse.core.types import Interval
from marketpulse.storage import tables as t
from marketpulse.storage.models import Candle, CandleGap
from marketpulse.storage.sqlite_base import SqliteBase

UPSERT_CHUNK = 500


def _row_to_candle(row: RowMapping) -> Candle:
    return Candle.model_validate(dict(row))


class CandlesMixin(SqliteBase):
    async def upsert_candles(self, candles: Sequence[Candle]) -> int:
        """Mumları idempotent yazar (aynı anahtar → güncelle). Yazılan satır sayısını döner."""
        if not candles:
            return 0
        written = 0
        async with self._engine.begin() as conn:
            for start in range(0, len(candles), UPSERT_CHUNK):
                chunk = candles[start : start + UPSERT_CHUNK]
                values = [c.model_dump() for c in chunk]
                stmt = sqlite_insert(t.candles).values(values)
                update_cols = {
                    col.name: getattr(stmt.excluded, col.name)
                    for col in t.candles.columns
                    if col.name not in {"symbol", "interval", "open_time"}
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        t.candles.c.symbol,
                        t.candles.c.interval,
                        t.candles.c.open_time,
                    ],
                    set_=update_cols,
                )
                await conn.execute(stmt)
                written += len(chunk)
        return written

    async def get_candles(
        self,
        symbol: str,
        interval: Interval,
        *,
        as_of: datetime | None = None,
        start: datetime | None = None,
        limit: int | None = None,
    ) -> list[Candle]:
        """`open_time` artan sırada mumlar.

        `as_of` verilirse yalnızca o anda **kapanmış** mumlar döner (`close_time <= as_of`);
        look-ahead korumasının tek kapısı budur. `limit` verilirse en yeni N mum alınır ve
        yine artan sırada döndürülür.
        """
        conditions: list[ColumnElement[bool]] = [
            t.candles.c.symbol == symbol,
            t.candles.c.interval == interval.value,
        ]
        if as_of is not None:
            conditions.append(t.candles.c.close_time <= as_of)
        if start is not None:
            conditions.append(t.candles.c.open_time >= start)
        order = t.candles.c.open_time.desc() if limit is not None else t.candles.c.open_time.asc()
        stmt = select(t.candles).where(*conditions).order_by(order)
        if limit is not None:
            stmt = stmt.limit(limit)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        candles = [_row_to_candle(r) for r in rows]
        if limit is not None:
            candles.reverse()
        return candles

    async def get_candle_closing_at(
        self, symbol: str, interval: Interval, close_time: datetime
    ) -> Candle | None:
        """Tam olarak `close_time` anında kapanan mum. Resolver bunu kullanır."""
        stmt = select(t.candles).where(
            t.candles.c.symbol == symbol,
            t.candles.c.interval == interval.value,
            t.candles.c.close_time == close_time,
        )
        async with self._engine.connect() as conn:
            row = (await conn.execute(stmt)).mappings().first()
        return None if row is None else _row_to_candle(row)

    async def latest_candle(
        self, symbol: str, interval: Interval, *, as_of: datetime | None = None
    ) -> Candle | None:
        candles = await self.get_candles(symbol, interval, as_of=as_of, limit=1)
        return candles[0] if candles else None

    async def count_candles(self, symbol: str, interval: Interval) -> int:
        stmt = select(func.count()).where(
            t.candles.c.symbol == symbol, t.candles.c.interval == interval.value
        )
        async with self._engine.connect() as conn:
            return int((await conn.execute(stmt)).scalar() or 0)

    async def find_candle_gaps(
        self, symbol: str, interval: Interval, *, since: datetime, until: datetime
    ) -> list[CandleGap]:
        """[since, until) aralığında eksik mum bloklarını bulur (open_time ızgarasına göre)."""
        step = interval.length
        stmt = (
            select(t.candles.c.open_time)
            .where(
                t.candles.c.symbol == symbol,
                t.candles.c.interval == interval.value,
                t.candles.c.open_time >= since,
                t.candles.c.open_time < until,
            )
            .order_by(t.candles.c.open_time)
        )
        async with self._engine.connect() as conn:
            present = {row[0] for row in (await conn.execute(stmt)).all()}
        gaps: list[CandleGap] = []
        cursor = since
        gap_start: datetime | None = None
        while cursor < until:
            if cursor in present:
                if gap_start is not None:
                    gaps.append(CandleGap(gap_start, cursor))
                    gap_start = None
            elif gap_start is None:
                gap_start = cursor
            cursor += step
        if gap_start is not None:
            gaps.append(CandleGap(gap_start, until))
        return gaps

    async def delete_candles_before(self, interval: Interval, before: datetime) -> int:
        async with self._engine.begin() as conn:
            result = await conn.execute(
                delete(t.candles).where(
                    t.candles.c.interval == interval.value, t.candles.c.open_time < before
                )
            )
        return int(result.rowcount or 0)
