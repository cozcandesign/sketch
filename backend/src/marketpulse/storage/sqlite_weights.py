"""Ağırlık tablosu erişimi (`weights`).

Aktif ağırlıklar burada tutulur. Tohumlama yalnızca tablo boşken yapılır: K3 gereği ağırlık
değişikliği kullanıcı onayına bağlıdır, sistem kendi kendine üzerine yazmaz.
"""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from marketpulse.core.types import Horizon
from marketpulse.storage import tables as t
from marketpulse.storage.sqlite_base import SqliteBase


class WeightsMixin(SqliteBase):
    """Ufuk bazlı modül ağırlıkları."""

    async def get_weights(self, horizon: Horizon) -> dict[str, float]:
        """Bir ufkun ağırlıkları; tablo boşsa boş sözlük (çağıran varsayılana düşer)."""
        stmt = select(t.weights.c.module, t.weights.c.weight).where(
            t.weights.c.horizon == horizon.value
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        return {str(row.module): float(row.weight) for row in rows}

    async def count_weights(self) -> int:
        async with self._engine.connect() as conn:
            total = (await conn.execute(select(func.count()).select_from(t.weights))).scalar()
        return int(total or 0)

    async def seed_weights(
        self,
        table: Mapping[Horizon, Mapping[str, float]],
        *,
        valid_from: datetime,
        source: str = "default",
    ) -> int:
        """Tablo boşsa varsayılanları yazar. Doluysa hiçbir şey yapmaz ve 0 döner."""
        if await self.count_weights() > 0:
            return 0
        rows = [
            {
                "horizon": horizon.value,
                "module": module,
                "weight": float(weight),
                "valid_from": valid_from,
                "source": source,
                "proposal_id": None,
            }
            for horizon, weights in table.items()
            for module, weight in weights.items()
        ]
        if not rows:
            return 0
        async with self._engine.begin() as conn:
            await conn.execute(sqlite_insert(t.weights), rows)
        return len(rows)
