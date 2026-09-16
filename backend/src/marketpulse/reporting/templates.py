"""Rapor cümle şablonları. Tüm insan-okunur rapor metni buradan üretilir (K4: LLM yok).

Her şablon `str.format` alanları kullanır ve yasak kelime testinden geçmek zorundadır. Sayılar
şablona **biçimlenmiş** (string) gelir; burada hesap yapılmaz.
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
    # --- teknik modül (ARCHITECTURE.md §8.2) ---
    "trend_up": "EMA dizilimi yukarı yönlü (fiyat > EMA20 > EMA50{ema200}); {context}",
    "trend_down": "EMA dizilimi aşağı yönlü (fiyat < EMA20 < EMA50{ema200}); {context}",
    "trend_mixed": "EMA dizilimi karışık, trend zayıf; {context}",
    "trend_context_same": "{tf} bağlamı aynı yönde",
    "trend_context_against": "{tf} bağlamı ters yönde",
    "trend_context_flat": "{tf} bağlamı yönsüz",
    "momentum": "RSI {rsi}; MACD histogramı {macd_tr}",
    "momentum_extreme": "RSI {rsi} aşırı bölgede; momentum katkısı yarıya indirildi",
    "volume_confirms": "Son {bars} bar hacmi 20 bar ortalamasının {ratio} katı: hareket destekli",
    "volume_weak": "Son {bars} bar hacmi ortalamanın {ratio} katı: hareketin hacim desteği zayıf",
    "volume_neutral": "Son {bars} bar hacmi 20 bar ortalaması düzeyinde ({ratio} kat)",
    "volume_above_value": "Fiyat hacim değer alanının üstünde (POC {poc})",
    "volume_below_value": "Fiyat hacim değer alanının altında (POC {poc})",
    "volume_inside_value": "Fiyat hacim değer alanının içinde (POC {poc}): denge bölgesi",
    "sr_resistance_near": (
        "Fiyat {distance} ATR altındaki {touches} dokunuşlu dirence yakın ({level})"
    ),
    "sr_support_near": "Fiyat {distance} ATR üstündeki {touches} dokunuşlu desteğe yakın ({level})",
    "sr_clear": "En yakın destek ve direnç 1 ATR'den uzak: seviye baskısı yok",
    "vol_squeeze": "Volatilite sıkışması (ATR yüzdelik {pct}): kırılım riski var, yön belirsiz",
    "vol_expansion": "Volatilite genişlemesi (ATR yüzdelik {pct}): hareket aralığı geniş",
}


def render(key: str, **fields: object) -> str:
    """Şablonu doldurur. Eksik alan `KeyError` verir; sessizce boş bırakılmaz."""
    return TEMPLATES[key].format(**fields)
