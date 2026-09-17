"""Haber tekilleştirme: aynı olayı bir kez sınıflandır, bir kez say (F4-2)."""

from datetime import UTC, datetime, timedelta

from marketpulse.llm.dedup import (
    assign_groups,
    group_news,
    jaccard,
    normalize_title,
)
from marketpulse.storage.models import NewsItem

NOW = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)


def item(
    title: str,
    *,
    source: str = "coindesk",
    minutes: int = 0,
    url: str | None = None,
    item_id: int | None = None,
) -> NewsItem:
    link = url or f"https://{source}.test/{abs(hash(title)) % 10_000}"
    return NewsItem(
        id=item_id,
        source=source,
        url=link,
        url_hash=f"{source}:{title}" if url is None else url,
        title=title,
        published_at=NOW + timedelta(minutes=minutes),
        fetched_at=NOW + timedelta(minutes=minutes),
    )


class TestTitleTokens:
    def test_drops_filler_words_and_punctuation(self) -> None:
        assert normalize_title("The SEC Approves a Bitcoin ETF!") == frozenset(
            {"sec", "approves", "bitcoin", "etf"}
        )

    def test_overlap_ratio(self) -> None:
        assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0
        assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == 1 / 3
        assert jaccard(frozenset(), frozenset({"a"})) == 0.0


def test_the_same_event_from_four_sources_becomes_one_group() -> None:
    """Dört kaynak aynı olayı yazdı: LLM'e bir kez gitmeli, modülde bir kez sayılmalı."""
    groups = group_news(
        [
            item("SEC approves spot Bitcoin ETF applications", source="coindesk", minutes=0),
            item("SEC approves spot Bitcoin ETF applications", source="theblock", minutes=4),
            item("SEC approves the spot Bitcoin ETF applications", source="decrypt", minutes=9),
            item(
                "Bitcoin spot ETF applications approved by SEC",
                source="cointelegraph",
                minutes=12,
            ),
        ]
    )

    assert len(groups) == 1
    assert groups[0].size == 4


def test_the_earliest_story_leads_the_group() -> None:
    """Grup başı ilk duyurandır: ufuk hesabı ilk duyuru anından işler."""
    groups = group_news(
        [
            item("Ether staking withdrawals queue lengthens", source="theblock", minutes=30),
            item("Ether staking withdrawals queue lengthens", source="coindesk", minutes=5),
        ]
    )

    assert groups[0].head.source == "coindesk"
    assert [member.source for member in groups[0].members] == ["theblock"]


def test_unrelated_stories_stay_apart() -> None:
    groups = group_news(
        [
            item("SEC approves spot Bitcoin ETF applications"),
            item("Solana network upgrade ships on mainnet"),
            item("Exchange outage hits traders in Asia"),
        ]
    )

    assert len(groups) == 3
    assert all(group.size == 1 for group in groups)


def test_the_same_headline_two_days_later_is_a_new_event() -> None:
    """48 saatlik pencere dışında eşleşme aranmaz: aynı başlık yeni bir olayı anlatıyordur."""
    groups = group_news(
        [
            item("Bitcoin falls below key support", source="coindesk", minutes=0),
            item("Bitcoin falls below key support", source="theblock", minutes=60 * 60),
        ]
    )

    assert len(groups) == 2


def test_the_same_url_always_lands_in_the_same_group() -> None:
    """Aynı bağlantı iki feed'den gelse başlıkları farklı yazılmış olsa da tek olaydır."""
    url = "https://www.coindesk.com/markets/2026/09/17/story"
    groups = group_news(
        [
            item("Markets wrap", url=url, minutes=0),
            item("Completely different wording here", url=url, minutes=20),
        ]
    )

    assert len(groups) == 1
    assert groups[0].size == 2


def test_only_the_head_is_marked_for_classification() -> None:
    groups = group_news(
        [
            item("SEC approves spot Bitcoin ETF", source="coindesk", minutes=0, item_id=1),
            item("SEC approves spot Bitcoin ETF", source="theblock", minutes=3, item_id=2),
            item("Solana upgrade ships", source="decrypt", minutes=5, item_id=3),
        ]
    )

    assignment = assign_groups(groups)

    assert assignment["coindesk:SEC approves spot Bitcoin ETF"] == (1, True)
    assert assignment["theblock:SEC approves spot Bitcoin ETF"] == (1, False)  # miras alır
    assert assignment["decrypt:Solana upgrade ships"] == (3, True)


def test_unwritten_items_are_left_out_of_the_assignment() -> None:
    """Kimliği olmayan (henüz yazılmamış) haber atama tablosuna girmez: uydurma kimlik üretilmez."""
    groups = group_news([item("Story without an id", item_id=None)])

    assert assign_groups(groups) == {}
