"""Karşıt argüman (ARCHITECTURE.md §10).

Her tahminin yanında "beni yanıltacak şey şu" cümlesi bulunur. Amaç kullanıcıya kendi kararını
verdirmek: sistem yalnızca lehte kanıtı göstererek kendine güven telkin etmez.

Seçim sırası:
1. Tahmin yönünün **tersine** işaret eden en güçlü alt bileşen (modül ağırlığıyla ölçülür),
2. yoksa volatilite sıkışması (kırılım yönü belirsiz),
3. yoksa düşük veri kapsamı,
4. hiçbiri yoksa genel şablon (ani hareket / sınıflandırılmamış haber şoku).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from marketpulse.reporting.templates import component_tr, module_tr, render
from marketpulse.signals.base import NON_DIRECTIONAL_COMPONENTS, SignalResult

MATERIAL: Final = 0.05  # bu büyüklüğün altındaki ters bileşen kayda değer sayılmaz
LOW_COVERAGE: Final = 0.6
SQUEEZE_THRESHOLD: Final = -0.8  # vol_regime ölçeği: -1 sıkışma, +1 genişleme


@dataclass(frozen=True)
class CounterArgument:
    text: str
    source: str  # "component" | "squeeze" | "coverage" | "default"


def build(
    results: Sequence[SignalResult],
    effective_weights: Mapping[str, float],
    *,
    p_up: float,
) -> CounterArgument:
    """Tahmin yönünün tersini gösteren en güçlü gerekçeyi seçer."""
    direction = 1.0 if p_up >= 0.5 else -1.0
    opposing = _strongest_opposing(results, effective_weights, direction)
    if opposing is not None:
        module, component, score = opposing
        return CounterArgument(
            render(
                "counter_component",
                module_tr=module_tr(module),
                component_tr=component_tr(component),
                score=f"{score:+.2f}",
            ),
            "component",
        )
    if _in_squeeze(results):
        return CounterArgument(render("counter_squeeze"), "squeeze")
    coverage = _weighted_coverage(results, effective_weights)
    if coverage < LOW_COVERAGE:
        return CounterArgument(
            render("counter_low_coverage", coverage=f"%{coverage * 100:.0f}"), "coverage"
        )
    return CounterArgument(render("counter_default"), "default")


def _strongest_opposing(
    results: Sequence[SignalResult],
    effective_weights: Mapping[str, float],
    direction: float,
) -> tuple[str, str, float] | None:
    """`|bileşen| × modül ağırlığı` en büyük olan ters bileşen."""
    best: tuple[str, str, float] | None = None
    best_strength = MATERIAL
    for result in results:
        weight = effective_weights.get(result.module, 0.0)
        if weight <= 0:
            continue
        for component, score in result.components.items():
            if component in NON_DIRECTIONAL_COMPONENTS:
                continue  # yönü yok, tersi de yok (ör. volatilite rejimi)
            if score * direction >= 0:  # aynı yönde: karşıt argüman değil
                continue
            strength = abs(score) * weight
            if strength > best_strength:
                best_strength = strength
                best = (result.module, component, score)
    return best


def _in_squeeze(results: Sequence[SignalResult]) -> bool:
    return any(result.components.get("vol_regime", 0.0) <= SQUEEZE_THRESHOLD for result in results)


def _weighted_coverage(
    results: Sequence[SignalResult], effective_weights: Mapping[str, float]
) -> float:
    total = sum(effective_weights.get(result.module, 0.0) for result in results)
    if total <= 0:
        return 0.0
    return (
        sum(result.coverage * effective_weights.get(result.module, 0.0) for result in results)
        / total
    )
