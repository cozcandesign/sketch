"""Haber tekilleştirme (ARCHITECTURE.md §12, LLM'den **önce** çalışır).

Aynı olay dört kaynaktan dört haber olarak gelir. Hepsini sınıflandırmak parayı dörde katlar ve
haber modülünde aynı olayı dört kez saydırır — ikisi de yanlıştır. Bu yüzden benzer haberler tek
gruba toplanır, yalnızca **grup başı** LLM'e gider, diğerleri sonucu ondan miras alır.

Saf modül: ağ ve DB erişimi yoktur. Girdi haber listesi, çıktı grup atamaları.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from marketpulse.storage.models import NewsItem

# Bu orandan fazla ortak kelimesi olan iki başlık aynı olayı anlatıyor sayılır.
JACCARD_THRESHOLD: Final = 0.6
# Bu kadar eski bir haberle eşleşme aranmaz: aynı başlık iki gün sonra yeni bir olaydır.
DEDUP_WINDOW: Final = timedelta(hours=48)
# Her başlıkta geçen kelimeler ayırt etmez; benzerliği yapay olarak şişirirler.
STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "and",
        "or",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "by",
        "with",
        "from",
        "after",
        "over",
        "its",
        "it",
        "this",
        "that",
        "has",
        "have",
        "will",
        "says",
        "say",
        "amid",
        "new",
        "up",
        "down",
    }
)
_WORD_RE: Final = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Group:
    """Bir dedup grubu: grup başı ve ona bağlanan haberler."""

    head: NewsItem
    members: tuple[NewsItem, ...] = ()

    @property
    def size(self) -> int:
        return 1 + len(self.members)


def normalize_title(title: str) -> frozenset[str]:
    """Başlığı ayırt edici kelimelere indirger: küçük harf, noktalama ve dolgu kelimeler atılır."""
    words = _WORD_RE.findall(title.lower())
    return frozenset(word for word in words if word not in STOPWORDS and len(word) > 1)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """İki kelime kümesinin örtüşme oranı: |kesişim| / |birleşim|. Boş küme → 0."""
    if not left or not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def group_news(
    items: Sequence[NewsItem],
    *,
    threshold: float = JACCARD_THRESHOLD,
    window: timedelta = DEDUP_WINDOW,
) -> list[Group]:
    """Haberleri gruplara ayırır.

    Grup başı **en erken yayınlanan** haberdir: olayı ilk duyuran kaynak, sonradan aynı olayı
    yazanlardan daha bilgilendiricidir ve ufuk hesabı ilk duyuru anından işler.

    Aynı URL'den gelen (aynı `url_hash`) haberler her koşulda aynı gruba düşer; başlık benzerliği
    yalnızca farklı kaynakları birbirine bağlamak için bakılır.
    """
    ordered = sorted(items, key=lambda item: (item.published_at, item.url_hash))
    groups: list[Group] = []
    tokens: list[frozenset[str]] = []
    members: list[list[NewsItem]] = []

    for item in ordered:
        item_tokens = normalize_title(item.title)
        index = _match_index(item, item_tokens, groups, tokens, threshold=threshold, window=window)
        if index is None:
            groups.append(Group(head=item))
            tokens.append(item_tokens)
            members.append([])
        else:
            members[index].append(item)

    return [
        Group(head=group.head, members=tuple(member_list))
        for group, member_list in zip(groups, members, strict=True)
    ]


def _match_index(
    item: NewsItem,
    item_tokens: frozenset[str],
    groups: Sequence[Group],
    tokens: Sequence[frozenset[str]],
    *,
    threshold: float,
    window: timedelta,
) -> int | None:
    """Haberin düşeceği grubun sırası; yenisi açılacaksa `None`.

    En yüksek benzerliğe sahip grup seçilir: eşiği geçen ilk grup değil, en yakın olan.
    """
    best: tuple[float, int] | None = None
    for index, group in enumerate(groups):
        if item.published_at - group.head.published_at > window:
            continue
        if item.url_hash == group.head.url_hash:
            return index
        score = jaccard(item_tokens, tokens[index])
        if score >= threshold and (best is None or score > best[0]):
            best = (score, index)
    return None if best is None else best[1]


def assign_groups(groups: Iterable[Group]) -> dict[str, tuple[int, bool]]:
    """`url_hash` → (grup kimliği, grup başı mı).

    Grup kimliği grup başının `news_items.id`'sidir; henüz yazılmamışsa sıra numarası kullanılamaz,
    bu yüzden çağıran taraf kimliği veritabanından verir.
    """
    assignment: dict[str, tuple[int, bool]] = {}
    for group in groups:
        head_id = group.head.id
        if head_id is None:
            continue
        assignment[group.head.url_hash] = (head_id, True)
        for member in group.members:
            assignment[member.url_hash] = (head_id, False)
    return assignment
