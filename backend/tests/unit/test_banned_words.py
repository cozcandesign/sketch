"""Yasak kelime testi (CLAUDE.md §1): şablonlar ve arayüz metinleri yönlendirici dil içeremez."""

import re
from pathlib import Path

import pytest

from marketpulse.reporting.banned_words import BANNED_WORDS, find_banned, normalize_tr, sanitize
from marketpulse.reporting.templates import TEMPLATES


def test_normalize_tr_handles_dotted_and_dotless_i() -> None:
    assert normalize_tr("KESİN") == "kesin"
    assert normalize_tr("ALIN") == "alın"
    assert normalize_tr("Kaçırma") == "kaçırma"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Şimdi al, kesin yükselecek", ["al", "kesin"]),
        ("Garanti fırsat, kaçırmayın!", ["garanti", "fırsat", "kaçırmayın"]),
        ("OI artarken fiyat yükseldi: gerçek alım baskısı", []),  # 'alım' yasak değil
        ("Satış hacmi arttı", []),  # 'satış' yasak değil
        ("", []),
    ],
)
def test_find_banned(text: str, expected: list[str]) -> None:
    assert find_banned(text) == expected


def test_sanitize_masks_only_banned_words() -> None:
    assert sanitize("Bu bir fırsat olabilir") == "Bu bir […] olabilir"
    assert sanitize("alım baskısı") == "alım baskısı"


def test_banned_list_is_lowercase_turkish() -> None:
    for word in BANNED_WORDS:
        assert word == normalize_tr(word)


def test_templates_contain_no_banned_words() -> None:
    for key, template in TEMPLATES.items():
        assert find_banned(template) == [], f"şablon {key!r} yasak kelime içeriyor"


_TS_STRING_RE = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`((?:[^`\\]|\\.)*)`")


def test_frontend_i18n_contains_no_banned_words(repo_root: Path) -> None:
    path = repo_root / "frontend" / "src" / "i18n" / "tr.ts"
    assert path.is_file(), f"arayüz metin dosyası yok: {path}"
    offenders: list[tuple[str, list[str]]] = []
    for match in _TS_STRING_RE.finditer(path.read_text(encoding="utf-8")):
        literal = next(g for g in match.groups() if g is not None)
        hits = find_banned(literal)
        if hits:
            offenders.append((literal, hits))
    assert offenders == [], f"tr.ts yasak kelime içeriyor: {offenders}"
