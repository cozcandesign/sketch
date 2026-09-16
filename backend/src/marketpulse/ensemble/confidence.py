"""Ensemble güveni (ARCHITECTURE.md §9.4).

```
agreement  = 1 − ağırlıklı_std(score_i)
coverage   = Σ w_i × coverage_i / Σ w_i
track      = Σ w_i × skill_i / Σ w_i         # geçmiş isabet; veri yoksa 0.75
regime     = 1 − 0.5 × (ATR yüzdelik > 0.9)
calendar   = 1 − 0.3 × (24 saat içinde importance-3 olay)
confidence = agreement^0.5 × coverage × track × regime × calendar
```

Etiket: `< 0.35 → low`, `< 0.6 → mid`, aksi `high`. Çelişki veya veto varsa etiket en fazla `low`.

**Tazelik burada ayrı çarpan değildir.** Her modül kendi `confidence`'ına tazeliği zaten işler
(ör. teknik modül bayat mumda güvenini düşürür) ve `e_i = w_i × c_i` üzerinden ensemble'a taşır;
ikinci kez çarpmak aynı cezayı iki kere uygulardı. ARCHITECTURE.md §9.4 bunu yansıtır.

Faz 2'de `track` için henüz kalibrasyon verisi yoktur (varsayılan 0.75 = "bilmiyorum") ve `calendar`
Faz 5'te takvim gelince devreye girer. Bu iki çarpan burada açıkça nötr bırakılır; gizli varsayım
değildir.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from marketpulse.ensemble.conflict import weighted_spread
from marketpulse.signals.base import SignalResult

ConfidenceLabel = Literal["low", "mid", "high"]

UNKNOWN_SKILL: Final = 0.75  # kalibrasyon verisi yokken "bilmiyorum"
LOW_MAX: Final = 0.35
MID_MAX: Final = 0.60
HIGH_VOL_PENALTY: Final = 0.5
CALENDAR_PENALTY: Final = 0.3


@dataclass(frozen=True)
class ConfidenceReading:
    value: float
    label: ConfidenceLabel
    parts: Mapping[str, float]


def evaluate(
    results: Sequence[SignalResult],
    effective_weights: Mapping[str, float],
    *,
    conflict_active: bool = False,
    veto_active: bool = False,
    skill: Mapping[str, float] | None = None,
    high_volatility: bool = False,
    calendar_event_near: bool = False,
) -> ConfidenceReading:
    """Modül sonuçlarından tek güven değeri ve etiketi üretir."""
    if not effective_weights:
        return ConfidenceReading(0.0, "low", {"coverage": 0.0})
    by_module: dict[str, SignalResult] = {result.module: result for result in results}
    scores: dict[str, float] = {
        name: by_module[name].score for name in effective_weights if name in by_module
    }
    agreement = max(0.0, 1.0 - weighted_spread(scores, effective_weights))
    coverage = _weighted({name: by_module[name].coverage for name in scores}, effective_weights)
    track = _weighted(
        {name: (skill or {}).get(name, UNKNOWN_SKILL) for name in scores}, effective_weights
    )
    regime = 1.0 - HIGH_VOL_PENALTY * high_volatility
    calendar = 1.0 - CALENDAR_PENALTY * calendar_event_near
    value = (agreement**0.5) * coverage * track * regime * calendar
    value = max(0.0, min(1.0, value))
    return ConfidenceReading(
        value=value,
        label=label_for(value, conflict_active=conflict_active, veto_active=veto_active),
        parts={
            "agreement": agreement,
            "coverage": coverage,
            "track": track,
            "regime": regime,
            "calendar": calendar,
        },
    )


def label_for(
    value: float, *, conflict_active: bool = False, veto_active: bool = False
) -> ConfidenceLabel:
    """Etiket; çelişki ya da veto varsa "low"un üstüne çıkamaz."""
    if conflict_active or veto_active:
        return "low"
    if value < LOW_MAX:
        return "low"
    if value < MID_MAX:
        return "mid"
    return "high"


def _weighted(values: Mapping[str, float], weights: Mapping[str, float]) -> float:
    total = sum(weights.get(name, 0.0) for name in values)
    if total <= 0:
        return 0.0
    return sum(values[name] * weights.get(name, 0.0) for name in values) / total
