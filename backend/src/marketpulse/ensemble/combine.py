"""Modül skorlarını tek olasılığa çevirir (ARCHITECTURE.md §9.2).

```
l_i  = k_h × score_i                  # skor → log-odds katkısı
e_i  = w_i × c_i                      # ağırlık × modül güveni; veri yoksa e_i = 0
L    = Σ e_i·l_i / Σ e_i              # etkin ağırlıklarla yeniden normalize
p_up = clip(sigmoid(L), 0.10, 0.90)   # K19: tevazu sınırı
```

`Σ e_i` ile bölme, "veri yok" diyen modülün ağırlığını kendiliğinden diğerlerine dağıtır: ayrı bir
yeniden dağıtım kodu yoktur, formülün kendisi bunu yapar.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from marketpulse.core.types import Horizon
from marketpulse.ensemble import conflict
from marketpulse.signals.base import SignalResult

# Ufuk başına log-odds ölçeği. 2.0 → tek modül skoru +1 iken p ≈ %88 (kırpma sonrası %88).
# Faz 8'de ufuk başına en az 300 çözümlenmiş tahminle fit edilip ÖNERİ olarak sunulur (K3).
DEFAULT_K: Final = 2.0
P_MIN: Final = 0.10
P_MAX: Final = 0.90
ENSEMBLE_VERSION: Final = "ensemble-v0"


@dataclass(frozen=True)
class EnsembleResult:
    """Birleştirmenin tüm ara değerleri — rapor ve hata ayıklama bunları kullanır."""

    p_up: float
    combined_score: float
    log_odds: float
    effective_weights: Mapping[str, float]
    contributions: Mapping[str, float]
    conflict: conflict.ConflictReading
    used_modules: tuple[str, ...]
    missing_modules: tuple[str, ...]
    weight_mass: float  # kullanılan etkin ağırlık / yapılandırılmış toplam ağırlık (0..1)

    @property
    def has_signal(self) -> bool:
        return bool(self.used_modules)


def clip_probability(probability: float) -> float:
    """K19: kalibrasyon kanıtlanana kadar olasılık [0.10, 0.90] aralığına kırpılır."""
    return min(P_MAX, max(P_MIN, probability))


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _weight_mass(effective: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Kanıt tabanının ne kadarı gerçekten var?

    Yeniden dağıtım (`Σ e_i` ile bölme) tek modülü %100 ağırlıkta gösterir; bu doğrudur ama
    "beş modülden dördü yok" bilgisini saklar. Bu oran o bilgiyi taşır ve güveni düşürür.
    """
    configured = sum(weight for weight in weights.values() if weight > 0)
    if configured <= 0:
        return 0.0
    return min(1.0, sum(effective.values()) / configured)


def combine(
    results: Sequence[SignalResult],
    weights: Mapping[str, float],
    *,
    horizon: Horizon,
    k: float = DEFAULT_K,
) -> EnsembleResult:
    """Modül sonuçlarını tek `p_up`'a indirger. `horizon` şimdilik yalnızca `k` seçimi içindir."""
    del horizon  # k ufka göre Faz 8'de ayrışacak; imza şimdiden sabit
    effective: dict[str, float] = {
        result.module: weights.get(result.module, 0.0) * result.confidence
        for result in results
        if result.has_data and weights.get(result.module, 0.0) * result.confidence > 0
    }
    scores: dict[str, float] = {result.module: result.score for result in results}
    missing = tuple(sorted(result.module for result in results if result.module not in effective))
    if not effective:
        return EnsembleResult(
            p_up=0.5,
            combined_score=0.0,
            log_odds=0.0,
            effective_weights={},
            contributions={},
            conflict=conflict.ConflictReading(False, 0.0, (), ()),
            used_modules=(),
            missing_modules=missing,
            weight_mass=0.0,
        )

    total = sum(effective.values())
    combined_score = sum(scores[name] * weight for name, weight in effective.items()) / total
    log_odds = k * combined_score
    reading = conflict.detect(scores, effective)
    probability = sigmoid(log_odds)
    if reading.active:
        probability = conflict.apply(probability)
    return EnsembleResult(
        p_up=clip_probability(probability),
        combined_score=combined_score,
        log_odds=log_odds,
        effective_weights=effective,
        contributions={
            name: weight / total * k * scores[name] for name, weight in effective.items()
        },
        conflict=reading,
        used_modules=tuple(sorted(effective)),
        missing_modules=missing,
        weight_mass=_weight_mass(effective, weights),
    )
