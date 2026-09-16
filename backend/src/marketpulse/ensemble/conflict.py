"""Çelişki tespiti (ARCHITECTURE.md §9.3).

Çelişki gizlenmez: modüller birbirine zıt şey söylüyorsa olasılık %50'ye çekilir, güven "düşük"ün
üstüne çıkamaz ve rapor bunu ilk maddede yazar. "Ortalamayı al, sorun yok" davranışı, zıt kanıtı
kullanıcıdan saklamak olurdu.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

MATERIAL_SCORE: Final = 0.3  # bu eşiğin altındaki skorlar "yön söylemiyor" sayılır
MAX_SPREAD: Final = 0.45  # ağırlıklı standart sapma bunun üstündeyse çelişki
PULL_TO_HALF: Final = 0.7  # p → 0.5 + 0.7 × (p − 0.5): %30 merkeze çekme


@dataclass(frozen=True)
class ConflictReading:
    active: bool
    spread: float
    positive: tuple[str, ...]
    negative: tuple[str, ...]


def detect(scores: Mapping[str, float], effective_weights: Mapping[str, float]) -> ConflictReading:
    """Hem yukarı hem aşağı diyen modül var mı, ya da dağılım çok mu geniş?"""
    voting = {name: score for name, score in scores.items() if effective_weights.get(name, 0) > 0}
    positive = tuple(sorted(n for n, s in voting.items() if s >= MATERIAL_SCORE))
    negative = tuple(sorted(n for n, s in voting.items() if s <= -MATERIAL_SCORE))
    spread = weighted_spread(voting, effective_weights)
    active = bool(positive and negative) or spread > MAX_SPREAD
    return ConflictReading(active=active, spread=spread, positive=positive, negative=negative)


def weighted_spread(scores: Mapping[str, float], effective_weights: Mapping[str, float]) -> float:
    """Skorların ağırlıklı standart sapması. Tek modül varsa 0 (dağılım tanımsız değil, yok)."""
    usable = [(scores[n], effective_weights.get(n, 0.0)) for n in scores]
    total = sum(weight for _, weight in usable)
    if total <= 0 or len(usable) < 2:
        return 0.0
    mean = sum(score * weight for score, weight in usable) / total
    variance = sum(weight * (score - mean) ** 2 for score, weight in usable) / total
    return math.sqrt(variance)


def apply(probability: float) -> float:
    """Çelişkide olasılığı %50'ye doğru %30 çeker."""
    return 0.5 + PULL_TO_HALF * (probability - 0.5)


def describe(reading: ConflictReading, modules_tr: Mapping[str, str]) -> tuple[str, str]:
    """Rapor cümlesi için (yukarı diyen modül, aşağı diyen modül) adlarını Türkçeleştirir."""
    up = reading.positive[0] if reading.positive else ""
    down = reading.negative[0] if reading.negative else ""
    return modules_tr.get(up, up), modules_tr.get(down, down)


def module_names(scores: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(scores))
