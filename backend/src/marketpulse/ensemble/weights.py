"""Ufuk bazlı modül ağırlıkları: YAML varsayılanı ve `weights` tablosu tohumu.

Sıra (ARCHITECTURE.md §9.1): aktif ağırlıklar `weights` tablosundan okunur; tablo boşsa YAML
yüklenir ve `source='default'` ile tohumlanır. Ağırlık değişimi K3 gereği yalnızca kullanıcı
onayıyla olur; bu modül kendiliğinden ağırlık güncellemez.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

import yaml

from marketpulse.core.types import Horizon
from marketpulse.signals.base import ModuleName

MODULES: Final[tuple[ModuleName, ...]] = (
    "technical",
    "orderflow",
    "news",
    "macro",
    "sentiment",
)
DEFAULT_PATH: Final = Path(__file__).resolve().parents[3] / "config" / "weights.default.yaml"

WeightTable = Mapping[Horizon, Mapping[str, float]]


def load_default_weights(path: Path | None = None) -> dict[Horizon, dict[str, float]]:
    """YAML'dan varsayılan ağırlıkları okur ve doğrular.

    Doğrulama: her ufuk için beş modül de bulunmalı, ağırlıklar negatif olmamalı ve toplamı
    pozitif olmalı. Eksik ya da bozuk dosya sessizce "hepsi sıfır" olmaz; `ValueError` fırlatır.
    """
    source = path or DEFAULT_PATH
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    horizons = cast("dict[str, dict[str, float]]", raw.get("horizons", {}))
    table: dict[Horizon, dict[str, float]] = {}
    for horizon in Horizon:
        values = horizons.get(horizon.value)
        if values is None:
            msg = f"ağırlık dosyasında ufuk eksik: {horizon.value} ({source})"
            raise ValueError(msg)
        table[horizon] = _validated(values, horizon, source)
    return table


def _validated(values: Mapping[str, float], horizon: Horizon, source: Path) -> dict[str, float]:
    missing = [module for module in MODULES if module not in values]
    if missing:
        msg = f"{horizon.value} ufkunda ağırlığı olmayan modül(ler): {missing} ({source})"
        raise ValueError(msg)
    weights: dict[str, float] = {module: float(values[module]) for module in MODULES}
    if any(weight < 0 for weight in weights.values()):
        msg = f"{horizon.value} ufkunda negatif ağırlık var ({source})"
        raise ValueError(msg)
    if sum(weights.values()) <= 0:
        msg = f"{horizon.value} ufkunda ağırlık toplamı sıfır ({source})"
        raise ValueError(msg)
    return weights
