"""Yasak kelime listesi (CLAUDE.md §1). Rapor şablonları ve arayüz metinleri bu listeyle taranır.

Kural: sistem yön OLASILIĞI raporlar; "al", "sat", "kesin", "garanti" gibi yönlendirici veya
kesinlik bildiren dil kullanmaz. Test: tests/unit/test_banned_words.py.
"""

import re
from typing import Final

BANNED_WORDS: Final[frozenset[str]] = frozenset(
    {
        "al",
        "alın",
        "sat",
        "satın",
        "kesin",
        "kesinlikle",
        "garanti",
        "garantili",
        "kaçırma",
        "kaçırmayın",
        "fırsat",
        "mutlaka",
    }
)

_TR_UPPER_TO_LOWER: Final = str.maketrans({"İ": "i", "I": "ı"})
_WORD_RE: Final = re.compile(r"[a-zçğıöşü]+", re.IGNORECASE)


def normalize_tr(text: str) -> str:
    """Türkçe'ye uygun küçük harfe çevirir (İ→i, I→ı) — `str.lower()` bunu yanlış yapar."""
    return text.translate(_TR_UPPER_TO_LOWER).lower()


def find_banned(text: str) -> list[str]:
    """Metindeki yasak kelimeleri (tam kelime eşleşmesi) sırayla döner; yoksa boş liste."""
    words = _WORD_RE.findall(normalize_tr(text))
    return [w for w in words if w in BANNED_WORDS]


def sanitize(text: str, replacement: str = "[…]") -> str:
    """LLM'den gelen serbest metindeki yasak kelimeleri maskeler (ARCHITECTURE.md §10)."""

    def _repl(match: re.Match[str]) -> str:
        return replacement if normalize_tr(match.group(0)) in BANNED_WORDS else match.group(0)

    return _WORD_RE.sub(_repl, text)
