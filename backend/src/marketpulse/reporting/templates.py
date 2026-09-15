"""Rapor cümle şablonları. Tüm insan-okunur rapor metni buradan üretilir (K4: LLM yok).

Faz 2'den itibaren modül şablonları eklenir. Her şablon `str.format` alanları kullanır ve
yasak kelime testinden geçmek zorundadır.
"""

from typing import Final

TEMPLATES: Final[dict[str, str]] = {
    "headline": "{symbol} · {horizon_tr} · Yukarı olasılığı %{p_up_pct} · Güven: {confidence_tr}",
    "conflict": (
        "Çelişkili sinyal: {module_a} {dir_a} derken {module_b} {dir_b} diyor; güven düşük."
    ),
    "veto_news": "⚠ VETO: büyük haber, teknik sinyaller ezildi: {title}",
    "veto_calendar": "⚠ VETO: {event} {when}; yön tahmini güvenilmez.",
    "counter_default": (
        "Beni yanıltacak şey: beklenen aralık dışına ani hareket veya "
        "sınıflandırılmamış bir haber şoku."
    ),
    "no_data": "{module}: veri yok ({reason}); ağırlığı diğer modüllere dağıtıldı.",
}


def render(key: str, **fields: object) -> str:
    """Şablonu doldurur. Eksik alan `KeyError` verir; sessizce boş bırakılmaz."""
    return TEMPLATES[key].format(**fields)
