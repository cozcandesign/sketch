"""Sinyal modülü sözleşmesi (ARCHITECTURE.md §8.1).

Modüller **saf fonksiyondur**: girdi `FeatureSnapshot`, çıktı `SignalResult`. Ağ, DB ve saat erişimi
yoktur; aynı girdi her zaman aynı çıktıyı verir. Bu, backtest ile canlının aynı kod yolunu
kullanabilmesinin (CLAUDE.md §9.5) ön koşuludur.

`score` yön ve şiddettir (-1 aşağı … +1 yukarı), `confidence` modülün kendi verisine güvenidir.
İkisi ayrıdır: güçlü ama az veriye dayanan bir skor, ensemble'da az ağırlık taşır.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from marketpulse.core.types import Horizon
from marketpulse.features.snapshot import FeatureSnapshot

ModuleName = Literal["technical", "orderflow", "news", "macro", "sentiment"]
VetoKind = Literal["news", "calendar"]

# Yön taşımayan bileşenler: skora katkı vermezler, yalnızca güveni ve beklenen aralığı etkiler.
# Karşıt argüman bunları "ters yönde bileşen" saymamalı — yönleri olmadığı için tersi de yoktur.
NON_DIRECTIONAL_COMPONENTS: frozenset[str] = frozenset({"vol_regime"})


class VetoFlag(BaseModel):
    """Modülün "bu tahmine güvenme" uyarısı. Yalnızca news ve macro doldurur."""

    model_config = ConfigDict(frozen=True)

    kind: VetoKind
    direction: int = Field(ge=-1, le=1)  # -1 aşağı, +1 yukarı, 0 yön yok
    reason: str


class SignalResult(BaseModel):
    """Tek modülün tek ufuk için çıktısı."""

    model_config = ConfigDict(frozen=True)

    module: ModuleName
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    components: Mapping[str, float] = Field(default_factory=dict)
    rationale: tuple[str, ...] = ()
    veto: VetoFlag | None = None
    data_as_of: datetime | None = None

    @property
    def has_data(self) -> bool:
        """Kapsama sıfırsa modül "veri yok" demiştir; ensemble ağırlığını dağıtır."""
        return self.coverage > 0.0


@dataclass(frozen=True)
class Component:
    """Tek alt skor ve onu açıklayan cümle(ler). Modüller bunları birleştirip skor üretir."""

    score: float
    rationale: tuple[str, ...] = ()


class SignalModule(Protocol):
    """Her sinyal modülünün uyduğu arayüz."""

    name: ModuleName

    def compute(self, snapshot: FeatureSnapshot, horizon: Horizon) -> SignalResult: ...


def no_data(module: ModuleName, as_of: datetime | None = None) -> SignalResult:
    """Veri yokken dönülecek nötr sonuç. Skor 0, kapsama 0 → ensemble bu modülü saymaz."""
    return SignalResult(module=module, score=0.0, confidence=0.0, coverage=0.0, data_as_of=as_of)


def clip_score(value: float) -> float:
    """Alt skorları sözleşmenin sınırlarına çeker (-1..+1)."""
    return max(-1.0, min(1.0, value))


def weighted_score(components: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """`score = Σ w_i · component_i / Σ w_i` (ARCHITECTURE.md §8.1).

    Yalnızca hem `components` hem `weights` içinde olan bileşenler sayılır; hesaplanamayan bir
    bileşen (veri yok) toplam ağırlığın dışında kalır, sıfır sayılmaz.
    """
    usable = {name: weights[name] for name in components if weights.get(name, 0.0) > 0.0}
    total = sum(usable.values())
    if total <= 0:
        return 0.0
    combined = sum(components[name] * weight for name, weight in usable.items()) / total
    return clip_score(combined)
