"""Türev piyasa tabloları: funding, açık pozisyon, long/short, taker hacmi.

Hepsi idempotent upsert'tir: aynı `(symbol, ts)` iki kez yazılırsa satır güncellenir, çoğalmaz.
Collector'lar örtüşen pencereler çektiği için bu şarttır.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, Table, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from marketpulse.storage import tables as t
from marketpulse.storage.models import (
    FundingLive,
    FundingRate,
    Liquidation,
    LongShortPoint,
    OpenInterestPoint,
    OrderflowRow,
    TakerVolumePoint,
)
from marketpulse.storage.sqlite_base import SqliteBase


class OrderflowMixin(SqliteBase):
    """Türev metriklerinin yazımı ve point-in-time okuması."""

    async def upsert_funding_rates(self, rows: Sequence[FundingRate]) -> int:
        return await self._upsert(
            t.funding_rates, [row.model_dump() for row in rows], ("symbol", "funding_time")
        )

    async def upsert_funding_live(self, rows: Sequence[FundingLive]) -> int:
        return await self._upsert(
            t.funding_live, [row.model_dump() for row in rows], ("symbol", "ts")
        )

    async def upsert_open_interest(self, rows: Sequence[OpenInterestPoint]) -> int:
        return await self._upsert(
            t.open_interest, [row.model_dump() for row in rows], ("symbol", "ts")
        )

    async def upsert_long_short(self, rows: Sequence[LongShortPoint]) -> int:
        return await self._upsert(
            t.long_short_ratio, [row.model_dump() for row in rows], ("symbol", "ts", "kind")
        )

    async def upsert_taker_volume(self, rows: Sequence[TakerVolumePoint]) -> int:
        return await self._upsert(
            t.taker_volume, [row.model_dump() for row in rows], ("symbol", "ts")
        )

    async def upsert_orderflow(self, rows: Sequence[OrderflowRow]) -> int:
        """`orderflow_1m` satırlarını yazar.

        `None` alanlar yazılmaz: aynı dakikaya WS (işlem/kitap) ve REST (±%1 derinlik) ayrı ayrı
        yazar; biri diğerinin sütunlarını sıfırlamamalı.
        """
        payload = [row.model_dump(exclude_none=True) for row in rows]
        return await self._upsert(t.orderflow_1m, payload, ("symbol", "ts"))

    async def insert_liquidations(self, rows: Sequence[Liquidation]) -> int:
        """Ham likidasyonlar (otomatik id). Aynı olay iki kez gelirse tekrar yazılır; kümeleme
        Faz 14'te bu tabloyu okur ve zaman penceresiyle çalışır."""
        if not rows:
            return 0
        async with self._engine.begin() as conn:
            await conn.execute(t.liquidations.insert(), [row.model_dump() for row in rows])
        return len(rows)

    async def get_orderflow(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[OrderflowRow]:
        rows = await self._select(
            t.orderflow_1m, symbol, t.orderflow_1m.c.ts, as_of=as_of, start=start
        )
        return [OrderflowRow(**row) for row in rows]

    async def get_liquidations(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[Liquidation]:
        rows = await self._select(
            t.liquidations, symbol, t.liquidations.c.ts, as_of=as_of, start=start
        )
        return [Liquidation(**{k: v for k, v in row.items() if k != "id"}) for row in rows]

    async def get_funding_rates(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[FundingRate]:
        rows = await self._select(
            t.funding_rates, symbol, t.funding_rates.c.funding_time, as_of=as_of, start=start
        )
        return [FundingRate(**row) for row in rows]

    async def get_funding_live(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[FundingLive]:
        rows = await self._select(
            t.funding_live, symbol, t.funding_live.c.ts, as_of=as_of, start=start
        )
        return [FundingLive(**row) for row in rows]

    async def get_open_interest(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[OpenInterestPoint]:
        rows = await self._select(
            t.open_interest, symbol, t.open_interest.c.ts, as_of=as_of, start=start
        )
        return [OpenInterestPoint(**row) for row in rows]

    async def get_long_short(
        self,
        symbol: str,
        *,
        kind: str | None = None,
        as_of: datetime | None = None,
        start: datetime | None = None,
    ) -> list[LongShortPoint]:
        extra = [t.long_short_ratio.c.kind == kind] if kind is not None else []
        rows = await self._select(
            t.long_short_ratio,
            symbol,
            t.long_short_ratio.c.ts,
            as_of=as_of,
            start=start,
            extra=extra,
        )
        return [LongShortPoint(**row) for row in rows]

    async def get_taker_volume(
        self, symbol: str, *, as_of: datetime | None = None, start: datetime | None = None
    ) -> list[TakerVolumePoint]:
        rows = await self._select(
            t.taker_volume, symbol, t.taker_volume.c.ts, as_of=as_of, start=start
        )
        return [TakerVolumePoint(**row) for row in rows]

    async def _upsert(
        self, table: Table, values: list[dict[str, object]], keys: tuple[str, ...]
    ) -> int:
        if not values:
            return 0
        async with self._engine.begin() as conn:
            for row in values:
                stmt = sqlite_insert(table).values(**row)
                updates = {k: v for k, v in row.items() if k not in keys}
                await conn.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[table.c[key] for key in keys], set_=updates
                    )
                    if updates
                    else stmt.on_conflict_do_nothing(index_elements=[table.c[key] for key in keys])
                )
        return len(values)

    async def _select(
        self,
        table: Table,
        symbol: str,
        time_column: ColumnElement[datetime],
        *,
        as_of: datetime | None,
        start: datetime | None,
        extra: list[ColumnElement[bool]] | None = None,
    ) -> list[dict[str, object]]:
        """`as_of` kesmesi burada uygulanır (CLAUDE.md §9.3): `ts <= as_of`."""
        conditions: list[ColumnElement[bool]] = [table.c.symbol == symbol, *(extra or [])]
        if as_of is not None:
            conditions.append(time_column <= as_of)
        if start is not None:
            conditions.append(time_column >= start)
        stmt = select(table).where(*conditions).order_by(time_column)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [dict(row) for row in rows]
