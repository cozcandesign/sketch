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
    # "Fiyat 0.4 ATR altındaki dirence yakın" iki yöne de okunabiliyordu; seviyenin nerede
    # olduğunu doğrudan söylüyoruz.
    "sr_resistance_near": "Direnç {distance} ATR yukarıda: {level} ({touches} dokunuş)",
    "sr_support_near": "Destek {distance} ATR aşağıda: {level} ({touches} dokunuş)",
    "sr_clear": "En yakın destek ve direnç 1 ATR'den uzak: seviye baskısı yok",
    "vol_squeeze": "Volatilite sıkışması (ATR yüzdelik {pct}): kırılım riski var, yön belirsiz",
    "vol_expansion": "Volatilite genişlemesi (ATR yüzdelik {pct}): hareket aralığı geniş",
    # --- order flow modülü (ARCHITECTURE.md §8.3) ---
    "funding_neutral": "Funding {rate}: olağan aralıkta, taraflardan biri kalabalık değil",
    "funding_long_crowded": (
        "Funding {rate} ({z}σ): long tarafı kalabalık; kalabalık taraf genelde ters yönde öder"
    ),
    "funding_short_crowded": (
        "Funding {rate} ({z}σ): short tarafı kalabalık; kalabalık taraf genelde ters yönde öder"
    ),
    "oi_real_buying": (
        "Açık pozisyon {oi_pct} artarken fiyat {price_pct} yükseldi: yeni alım pozisyonu giriyor"
    ),
    "oi_short_building": (
        "Açık pozisyon {oi_pct} artarken fiyat {price_pct} geriledi: short birikimi"
    ),
    "oi_short_covering": (
        "Açık pozisyon {oi_pct} azalırken fiyat {price_pct} yükseldi: short kapanışı (zayıf sinyal)"
    ),
    "oi_long_unwinding": (
        "Açık pozisyon {oi_pct} azalırken fiyat {price_pct} geriledi: long çözülüyor (zayıf sinyal)"
    ),
    "liq_quiet": "Pencerede kayda değer zorunlu kapatma yok",
    "liq_short": "Zorunlu kapatmaların ağırlığı short tarafta ({side_usd} / {usd}): zorunlu alım",
    "liq_long": "Zorunlu kapatmaların ağırlığı long tarafta ({side_usd} / {usd}): zorunlu satış",
    "liq_capitulation": (
        "Zorunlu kapatma hacmi olağanın 3 katını aştı ({usd}): tükeniş olasılığı, "
        "işaret ters çevrildi"
    ),
    "book_bid_heavy": "Order book alış tarafında yoğun ({pct} dengesizlik)",
    "book_ask_heavy": "Order book satış tarafında yoğun ({pct} dengesizlik)",
    "cvd_flow": "Agresif işlemlerin net yönü {pct} (hacme oranla)",
    "cvd_aligned": "Agresif akış ({pct}) fiyat yönüyle uyumlu: teyit, yeni bilgi az",
    "cvd_absorption": "Fiyat gerilerken agresif alım sürüyor ({pct}): birikim işareti",
    "cvd_distribution": "Fiyat yükselirken agresif satış sürüyor ({pct}): dağıtım işareti",
    # --- karşıt argüman (ARCHITECTURE.md §10) ---
    "counter_component": (
        "Beni yanıltacak şey: {module_tr} modülünde {component_tr} tahminin tersine işaret "
        "ediyor (skor {score}); bu bileşen ağır basarsa yön değişir."
    ),
    "counter_squeeze": (
        "Beni yanıltacak şey: volatilite sıkışmış; kırılım her iki yöne de olabilir ve "
        "sıkışma sonrası hareket beklenen aralığı aşabilir."
    ),
    "counter_low_coverage": (
        "Beni yanıltacak şey: veri kapsamı düşük ({coverage}); eksik veri yön hatası üretebilir."
    ),
    # --- rapor gövdesi ---
    "reason_line": "{module_tr}: {text}",
}


MODULE_TR: Final[dict[str, str]] = {
    "technical": "teknik",
    "orderflow": "order flow",
    "news": "haber",
    "macro": "makro",
    "sentiment": "duyarlılık",
}

COMPONENT_TR: Final[dict[str, str]] = {
    "trend": "trend",
    "momentum": "momentum",
    "volume": "hacim",
    "sr": "destek/direnç",
    "vol_regime": "volatilite rejimi",
}

CONFIDENCE_TR: Final[dict[str, str]] = {"low": "düşük", "mid": "orta", "high": "yüksek"}


def render(key: str, **fields: object) -> str:
    """Şablonu doldurur. Eksik alan `KeyError` verir; sessizce boş bırakılmaz."""
    return TEMPLATES[key].format(**fields)


def module_tr(module: str) -> str:
    return MODULE_TR.get(module, module)


def component_tr(component: str) -> str:
    return COMPONENT_TR.get(component, component)
