"""RSS toplayıcısı: kanonik URL, tarih normalizasyonu, koşullu istek, idempotent yazım (F4-1)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from marketpulse.collectors.rss import (
    CURSOR_SETTING_PREFIX,
    Feed,
    RssCollector,
    canonical_url,
    url_hash,
)
from marketpulse.core.clock import FakeClock
from marketpulse.storage import SqliteRepository, make_engine
from tests.fixtures.feeds import ATOM_ONE_ITEM, RSS_MESSY, RSS_TWO_ITEMS

NOW = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
FEED = Feed("coindesk", "https://feeds.test/coindesk.xml")


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    repository = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repository.create_all()
    yield repository
    await repository.close()


def build(repo: SqliteRepository, clock: FakeClock, http: httpx.AsyncClient) -> RssCollector:
    return RssCollector(repo, clock, http, feeds=[FEED])


class TestCanonicalUrl:
    def test_drops_tracking_parameters_and_fragment(self) -> None:
        messy = "https://Site.test/a/b/?utm_source=x&id=7&fbclid=z#top"
        assert canonical_url(messy) == "https://site.test/a/b?id=7"

    def test_ignores_trailing_slash_and_parameter_order(self) -> None:
        # Aynı haberin iki yazımı tek satır olmalı: aksi hâlde LLM'e iki kez para ödenir.
        assert url_hash("https://site.test/a?b=1&a=2") == url_hash("https://site.test/a/?a=2&b=1")

    def test_different_articles_keep_different_hashes(self) -> None:
        assert url_hash("https://site.test/a") != url_hash("https://site.test/b")


@respx.mock
async def test_writes_items_with_normalised_fields(repo: SqliteRepository) -> None:
    respx.get(FEED.url).mock(return_value=httpx.Response(200, text=RSS_TWO_ITEMS))
    async with httpx.AsyncClient() as http:
        written = await build(repo, FakeClock(NOW), http).poll()

    assert written == 2
    items = await repo.get_news()
    assert [item.title for item in items] == [
        "Ether staking withdrawals queue lengthens",
        "Bitcoin holds above key level as ETF flows turn positive",  # published_at sırası
    ]
    etf = items[1]
    assert etf.url == "https://www.coindesk.com/markets/2026/09/17/btc-etf-flows"  # utm_* atıldı
    assert etf.published_at == datetime(2026, 9, 17, 8, 30, tzinfo=UTC)
    assert etf.fetched_at == NOW
    assert etf.summary == "Spot bitcoin funds recorded net inflows for a third day."  # HTML yok
    assert etf.source == "coindesk"


@respx.mock
async def test_atom_feeds_are_read_too(repo: SqliteRepository) -> None:
    respx.get(FEED.url).mock(return_value=httpx.Response(200, text=ATOM_ONE_ITEM))
    async with httpx.AsyncClient() as http:
        assert await build(repo, FakeClock(NOW), http).poll() == 1

    item = (await repo.get_news())[0]
    assert item.published_at == datetime(2026, 9, 17, 9, 15, tzinfo=UTC)
    assert item.url == "https://decrypt.co/1234/solana-upgrade"


@respx.mock
async def test_messy_entries_are_skipped_not_crashed(repo: SqliteRepository) -> None:
    """Başlıksız girdi atlanır; tarihsiz girdi alınma anını alır; çok eski haber alınmaz."""
    respx.get(FEED.url).mock(return_value=httpx.Response(200, text=RSS_MESSY))
    async with httpx.AsyncClient() as http:
        assert await build(repo, FakeClock(NOW), http).poll() == 1

    items = await repo.get_news()
    assert [item.title for item in items] == ["Exchange outage reported"]
    assert items[0].published_at == NOW


@respx.mock
async def test_the_same_story_is_not_written_twice(repo: SqliteRepository) -> None:
    """Feed her turda aynı haberleri verir; ikinci tur yeni satır yazmamalı."""
    respx.get(FEED.url).mock(return_value=httpx.Response(200, text=RSS_TWO_ITEMS))
    clock = FakeClock(NOW)
    async with httpx.AsyncClient() as http:
        collector = build(repo, clock, http)
        assert await collector.poll() == 2
        clock.set(NOW + timedelta(minutes=3))
        assert await collector.poll() == 0

    items = await repo.get_news()
    assert len(items) == 2
    # İlk görülme anı korunur: look-ahead denetiminin dayanağı budur.
    assert all(item.fetched_at == NOW for item in items)


@respx.mock
async def test_conditional_request_uses_the_stored_validators(repo: SqliteRepository) -> None:
    route = respx.get(FEED.url).mock(
        return_value=httpx.Response(
            200,
            text=RSS_TWO_ITEMS,
            headers={"ETag": '"abc123"', "Last-Modified": "Thu, 17 Sep 2026 08:31:00 GMT"},
        )
    )
    async with httpx.AsyncClient() as http:
        collector = build(repo, FakeClock(NOW), http)
        await collector.poll()
        route.mock(return_value=httpx.Response(304))
        assert await collector.poll() == 0

    stored = await repo.get_setting(CURSOR_SETTING_PREFIX + FEED.source)
    assert stored == {"etag": '"abc123"', "last_modified": "Thu, 17 Sep 2026 08:31:00 GMT"}
    second = route.calls[1].request
    assert second.headers["If-None-Match"] == '"abc123"'
    assert second.headers["If-Modified-Since"] == "Thu, 17 Sep 2026 08:31:00 GMT"


@respx.mock
async def test_a_broken_feed_does_not_stop_the_others(repo: SqliteRepository) -> None:
    """Collector istisna sızdırmaz (CLAUDE.md §6): biri 500 dönse de diğeri toplanır."""
    other = Feed("decrypt", "https://feeds.test/decrypt.xml")
    respx.get(FEED.url).mock(return_value=httpx.Response(500, text="bozuk"))
    respx.get(other.url).mock(return_value=httpx.Response(200, text=ATOM_ONE_ITEM))
    async with httpx.AsyncClient() as http:
        collector = RssCollector(repo, FakeClock(NOW), http, feeds=[FEED, other])
        assert await collector.poll() == 1


@respx.mock
async def test_a_network_error_is_swallowed(repo: SqliteRepository) -> None:
    respx.get(FEED.url).mock(side_effect=httpx.ConnectError("ağ yok"))
    async with httpx.AsyncClient() as http:
        assert await build(repo, FakeClock(NOW), http).poll() == 0


@respx.mock
async def test_news_is_read_by_when_we_learned_it_not_when_it_was_published(
    repo: SqliteRepository,
) -> None:
    """`as_of` kesmesi `fetched_at`'e bakar: yayın anında bilmiş gibi davranmak look-ahead olur."""
    respx.get(FEED.url).mock(return_value=httpx.Response(200, text=RSS_TWO_ITEMS))
    async with httpx.AsyncClient() as http:
        await build(repo, FakeClock(NOW), http).poll()

    assert await repo.get_news(as_of=NOW - timedelta(seconds=1)) == []
    assert len(await repo.get_news(as_of=NOW)) == 2
