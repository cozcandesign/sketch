"""RSS haber toplayıcısı (ARCHITECTURE.md §4).

Dört kaynak: CoinDesk, The Block, Cointelegraph, Decrypt. Her tur `ETag` / `Last-Modified` ile
koşullu istek yapar; feed değişmediyse sunucu `304` döner ve gövde indirilmez.

**Bu collector içerik yorumlamaz.** Yalnızca haberi kaydeder: başlık, özet, yayın zamanı, kaynak.
Sınıflandırma (Kademe 1/2) ayrı işlerdir ve haber metnini **veri** olarak görür, talimat olarak
değil (CLAUDE.md §13).

Collector istisna sızdırmaz: bir feed bozulursa diğerleri toplanmaya devam eder.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.storage.models import FeedCursor, NewsItem
from marketpulse.storage.repository import Repository

COLLECTOR_NAME: Final = "rss"
CURSOR_SETTING_PREFIX: Final = "rss_cursor:"
REQUEST_TIMEOUT_SEC: Final = 20.0
USER_AGENT: Final = "MarketPulse/0.1 (personal analysis tool)"
# Bir turda bir feed'den alınacak en fazla haber: feed birdenbire yüzlerce eski kayıt verirse
# LLM kuyruğunu doldurmasın.
MAX_ITEMS_PER_FEED: Final = 50
# Bundan eski haberler alınmaz: ilk açılışta feed'in arşivi tahmin penceresiyle alakasızdır.
MAX_AGE: Final = timedelta(days=2)
# İzleme parametreleri URL'i farklı gösterir ama haber aynıdır (§ dedup).
TRACKING_PREFIXES: Final = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source")


@dataclass(frozen=True)
class Feed:
    """Tek bir RSS kaynağı. `source` veritabanına yazılan kısa addır."""

    source: str
    url: str


DEFAULT_FEEDS: Final[tuple[Feed, ...]] = (
    Feed("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    Feed("theblock", "https://www.theblock.co/rss.xml"),
    Feed("cointelegraph", "https://cointelegraph.com/rss"),
    Feed("decrypt", "https://decrypt.co/feed"),
)


def canonical_url(url: str) -> str:
    """İzleme parametrelerini, fragment'i ve sondaki `/` işaretini atar.

    Aynı haberin `?utm_source=twitter` ile gelen hâli ile çıplak hâli tek satır olmalı.
    Sorgu parametrelerinin sırası da sabitlenir: sıra farkı yeni haber sayılmasın.
    """
    parsed = urlparse(url.strip())
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(TRACKING_PREFIXES)
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", urlencode(sorted(kept)), "")
    )


def url_hash(url: str) -> str:
    """Kanonik URL'in SHA-256'sı: `news_items.url_hash` benzersizlik anahtarı."""
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()


def parse_published(entry: Any, *, fallback: datetime) -> datetime:
    """Girdinin yayın zamanı (UTC). Feed tarih vermezse `fallback` (alınma anı) kullanılır.

    `feedparser` tarihi `struct_time` olarak UTC'ye çevirerek verir; alan yoksa `None` olur.
    Gelecekte görünen tarihler (kaynak saatinin ileri olması) alınma anına çekilir: haberin
    ufuk hesabında geleceğe düşmesi look-ahead'e kapı açar (§9.3).
    """
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None) or (
            entry.get(field) if isinstance(entry, dict) else None
        )
        if value is None:
            continue
        try:
            year, month, day, hour, minute, second = (int(part) for part in tuple(value)[:6])
            stamp = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
        except (TypeError, ValueError):
            continue
        return min(stamp, fallback)
    return fallback


class RssCollector:
    """Dört feed'i tarar, yeni haberleri `news_items`'a yazar."""

    name = COLLECTOR_NAME

    def __init__(
        self,
        repo: Repository,
        clock: Clock,
        http: httpx.AsyncClient,
        *,
        feeds: Sequence[Feed] = DEFAULT_FEEDS,
        max_age: timedelta = MAX_AGE,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._http = http
        self._feeds = list(feeds)
        self._max_age = max_age

    async def poll(self) -> int:
        """Tüm feed'leri bir kez tarar. Yazılan **yeni** haber sayısını döner."""
        written = 0
        for feed in self._feeds:
            written += await self._poll_feed(feed)
        return written

    async def _poll_feed(self, feed: Feed) -> int:
        """Tek feed. Hata yükseltmez: bir kaynak bozulursa diğerleri toplanır (CLAUDE.md §6)."""
        try:
            cursor = await self._read_cursor(feed)
            response = await self._http.get(
                feed.url, headers=_conditional_headers(cursor), timeout=REQUEST_TIMEOUT_SEC
            )
        except httpx.HTTPError as exc:
            logger.bind(collector=self.name, feed=feed.source).warning(
                "feed alınamadı: {e}", e=repr(exc)
            )
            return 0
        if response.status_code == 304:  # değişmemiş
            return 0
        if response.status_code >= 400:
            logger.bind(collector=self.name, feed=feed.source).warning(
                "feed {code} döndü", code=response.status_code
            )
            return 0

        items = self._items_from(feed, response.text)
        written = await self._repo.upsert_news(items)
        await self._write_cursor(feed, response)
        if written:
            logger.bind(collector=self.name, feed=feed.source).info("{n} yeni haber", n=written)
        return written

    def _items_from(self, feed: Feed, body: str) -> list[NewsItem]:
        """Feed gövdesini haber satırlarına çevirir; çok eski ve başlıksız girdiler atlanır."""
        now = self._clock.now()
        oldest = now - self._max_age
        parsed = feedparser.parse(body)
        items: list[NewsItem] = []
        for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
            link = str(entry.get("link") or "").strip()
            title = str(entry.get("title") or "").strip()
            if not link or not title:
                continue
            published = parse_published(entry, fallback=now)
            if published < oldest:
                continue
            items.append(
                NewsItem(
                    source=feed.source,
                    url=canonical_url(link),
                    url_hash=url_hash(link),
                    title=title,
                    summary=_summary_of(entry),
                    published_at=published,
                    fetched_at=now,
                )
            )
        return items

    async def _read_cursor(self, feed: Feed) -> FeedCursor:
        raw = await self._repo.get_setting(CURSOR_SETTING_PREFIX + feed.source)
        if not isinstance(raw, dict):
            return FeedCursor()
        return FeedCursor(etag=raw.get("etag"), last_modified=raw.get("last_modified"))

    async def _write_cursor(self, feed: Feed, response: httpx.Response) -> None:
        """Koşullu istek başlıklarını saklar: bir sonraki tur değişmemişse gövde indirilmez."""
        cursor = FeedCursor(
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        if cursor.etag is None and cursor.last_modified is None:
            return
        await self._repo.set_setting(
            CURSOR_SETTING_PREFIX + feed.source, cursor.model_dump(), self._clock.now()
        )


def _conditional_headers(cursor: FeedCursor) -> dict[str, str]:
    # Yalnızca ASCII: HTTP başlık değerleri Türkçe karakter taşıyamaz (httpx encode edemez).
    headers = {"User-Agent": USER_AGENT}
    if cursor.etag:
        headers["If-None-Match"] = cursor.etag
    if cursor.last_modified:
        headers["If-Modified-Since"] = cursor.last_modified
    return headers


def _summary_of(entry: Any) -> str | None:
    """Özet alanı kaynaktan kaynağa değişir; ilk dolu olanı alınır, HTML etiketleri temizlenir."""
    for field in ("summary", "description", "subtitle"):
        value = entry.get(field) if isinstance(entry, dict) else getattr(entry, field, None)
        if isinstance(value, str) and value.strip():
            return _strip_html(value).strip() or None
    return None


def _strip_html(text: str) -> str:
    """Etiketleri kaba biçimde atar: özet LLM'e giden dış içeriktir, işaretleme taşımasın."""
    out: list[str] = []
    depth = 0
    for char in text:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return " ".join("".join(out).split())
