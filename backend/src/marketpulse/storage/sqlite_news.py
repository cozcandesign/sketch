"""Haber tabloları: `news_items` yazımı ve point-in-time okuması.

Yazım idempotenttir: aynı haber (aynı `url_hash`) tekrar gelirse satır çoğalmaz. Feed'ler
örtüşen pencereler verdiği için bu şarttır — bir haber her turda yeniden görünür.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from marketpulse.storage import tables as t
from marketpulse.storage.models import NewsItem
from marketpulse.storage.sqlite_base import SqliteBase


class NewsMixin(SqliteBase):
    async def upsert_news(self, rows: Sequence[NewsItem]) -> int:
        """Yeni haberleri yazar. Zaten bilinen `url_hash` **güncellenmez**.

        Neden güncellenmez: `fetched_at` ilk görülme anıdır ve look-ahead denetiminin dayanağıdır
        (§9.3). Her turda üzerine yazılsaydı eski bir haber "az önce geldi" görünür, dedup ve
        kademe kayıtları da yeniden tetiklenirdi. Yazılan **yeni** satır sayısını döner.
        """
        if not rows:
            return 0
        written = 0
        async with self._engine.begin() as conn:
            for row in rows:
                payload = row.model_dump(exclude={"id"})
                stmt = sqlite_insert(t.news_items).values(**payload)
                result = await conn.execute(
                    stmt.on_conflict_do_nothing(index_elements=[t.news_items.c.url_hash])
                )
                written += result.rowcount or 0
        return written

    async def get_news(
        self,
        *,
        as_of: datetime | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[NewsItem]:
        """Haberleri `published_at` sırasıyla döner.

        `as_of` verilirse yalnızca o ana kadar **alınmış** haberler döner (`fetched_at <= as_of`):
        kesme yayın anına göre değil, bizim öğrendiğimiz ana göre yapılır — bir haberi yayınlandığı
        saniyede bilmiş gibi davranmak look-ahead olurdu (§9.3).
        """
        stmt = select(t.news_items)
        if as_of is not None:
            stmt = stmt.where(t.news_items.c.fetched_at <= as_of)
        if since is not None:
            stmt = stmt.where(t.news_items.c.published_at >= since)
        stmt = stmt.order_by(t.news_items.c.published_at)
        if limit is not None:
            stmt = stmt.limit(limit)
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [NewsItem(**dict(row)) for row in rows]

    async def known_url_hashes(self, hashes: Sequence[str]) -> set[str]:
        """Verilenlerden hangileri zaten kayıtlı: LLM'e gitmeden önce eleme yapmak için."""
        if not hashes:
            return set()
        stmt = select(t.news_items.c.url_hash).where(t.news_items.c.url_hash.in_(list(hashes)))
        async with self._engine.connect() as conn:
            return {row[0] for row in (await conn.execute(stmt)).all()}

    async def delete_news_before(self, before: datetime) -> int:
        """Saklama süresi dolanları siler (K21: 180 gün). Kademe satırları CASCADE ile gider."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                delete(t.news_items).where(t.news_items.c.published_at < before)
            )
        return result.rowcount or 0
