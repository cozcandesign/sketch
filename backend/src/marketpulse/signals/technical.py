"""Teknik sinyal modülü (ARCHITECTURE.md §8.2).

Bileşenler ve modül içi sabit ağırlıklar:

| bileşen | ağırlık | ne ölçer |
|---|---|---|
| `trend` | 0.40 | EMA dizilimi + EMA50 eğimi, bağlam zaman dilimiyle doğrulanır |
| `momentum` | 0.30 | RSI ve MACD histogramı; aşırı bölgede sönümlenir |
| `volume` | 0.15 | hareketin hacim onayı ve hacim profiline göre konum |
| `sr` | 0.15 | 1 ATR içindeki mekanik destek/direnç |
| `vol_regime` | 0 | yön taşımaz; güveni ve beklenen aralığı etkiler |

Öznel çizgi yoktur: seviyeler yalnızca onaylanmış swing'lerden ve hacim profilinden gelir. Modül
saftır (ağ/DB/saat yok), bu yüzden aynı snapshot her zaman aynı sonucu verir.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import pandas as pd

from marketpulse.core.types import Horizon, Interval
from marketpulse.features import indicators as ind
from marketpulse.features import levels as lv
from marketpulse.features.snapshot import FeatureSnapshot
from marketpulse.reporting.templates import render
from marketpulse.signals.base import (
    ModuleName,
    SignalResult,
    clip_score,
    no_data,
    weighted_score,
)

COMPONENT_WEIGHTS: Final[Mapping[str, float]] = {
    "trend": 0.40,
    "momentum": 0.30,
    "volume": 0.15,
    "sr": 0.15,
    "vol_regime": 0.0,  # yön yok (ARCHITECTURE.md §8.2)
}

MIN_BARS: Final = 60  # RSI14 + MACD(26,9) + 20 barlık hacim ortalaması için asgari
REGIME_WINDOW_DAYS: Final = 90
SQUEEZE_PCT: Final = 0.10
EXPANSION_PCT: Final = 0.90
CONTEXT_SAME: Final = 1.2
CONTEXT_AGAINST: Final = 0.6
RSI_HIGH: Final = 80.0
RSI_LOW: Final = 20.0
VOLUME_FAST_BARS: Final = 5
VOLUME_SLOW_BARS: Final = 20
# Hacim onayı bandı: %10 sapmanın altı "ortalama düzeyde" sayılır, yön katkısı üretmez.
VOLUME_CONFIRM_RATIO: Final = 1.1
VOLUME_WEAK_RATIO: Final = 0.9
# Kapsama: ana zaman dilimi belirleyici, bağlam destekleyici.
BASE_COVERAGE_SHARE: Final = 0.75
MAX_RATIONALE: Final = 5


@dataclass(frozen=True)
class Component:
    """Tek alt skor ve onu açıklayan cümle(ler)."""

    score: float
    rationale: tuple[str, ...] = ()


class TechnicalModule:
    """`SignalModule` implementasyonu; durum tutmaz."""

    name: ModuleName = "technical"

    def compute(self, snapshot: FeatureSnapshot, horizon: Horizon) -> SignalResult:
        base = snapshot.frame(horizon.base_interval)
        if len(base) < MIN_BARS:
            return no_data(self.name, snapshot.as_of)
        atr_value = _last_float(ind.atr(base, 14))
        if atr_value is None or atr_value <= 0:
            return no_data(self.name, snapshot.as_of)

        context = snapshot.frame(horizon.context_interval)
        price = float(base["close"].iloc[-1])
        parts: dict[str, Component] = {
            "trend": _trend(base, context, atr_value, horizon.context_interval),
            "momentum": _momentum(base, atr_value),
            "volume": _volume(base, price),
            "sr": _sr(base, price, atr_value),
            "vol_regime": _vol_regime(base, horizon.base_interval),
        }
        scores = {name: part.score for name, part in parts.items()}
        score = weighted_score(scores, COMPONENT_WEIGHTS)
        squeeze = scores["vol_regime"] <= (SQUEEZE_PCT * 2 - 1)
        return SignalResult(
            module=self.name,
            score=score,
            confidence=_confidence(snapshot, horizon, scores, squeeze=squeeze),
            coverage=_coverage(snapshot, horizon),
            components=scores,
            rationale=_rationale(parts),
            data_as_of=snapshot.as_of,
        )


def _trend(
    base: pd.DataFrame, context: pd.DataFrame, atr_value: float, context_tf: Interval
) -> Component:
    """EMA dizilimi (±1 / ±0.3) + EMA50 eğimi (±0.3), bağlam zaman dilimiyle ölçeklenir."""
    close = base["close"]
    price = float(close.iloc[-1])
    ema20, ema50 = _last_float(ind.ema(close, 20)), _last_float(ind.ema(close, 50))
    if ema20 is None or ema50 is None:
        return Component(0.0)
    ema200 = _last_float(ind.ema(close, 200))
    alignment, key, note = _alignment(price, ema20, ema50, ema200)
    slope_series = ind.ema(close, 50)
    slope = (float(slope_series.iloc[-1]) - float(slope_series.iloc[-6])) / atr_value
    raw = alignment + max(-0.3, min(0.3, slope))

    context_score = _context_direction(context)
    factor, context_key = _context_factor(raw, context_score)
    text = render(key, ema200=note, context=render(context_key, tf=context_tf.value))
    return Component(clip_score(raw * factor), (text,))


def _alignment(
    price: float, ema20: float, ema50: float, ema200: float | None
) -> tuple[float, str, str]:
    """EMA dizilimi: tam yükseliş +1, tam düşüş −1, karışık ±0.3."""
    note = " > EMA200" if ema200 is not None else ""
    bullish = price > ema20 > ema50 and (ema200 is None or ema50 > ema200)
    bearish = price < ema20 < ema50 and (ema200 is None or ema50 < ema200)
    if bullish:
        return 1.0, "trend_up", note
    if bearish:
        return -1.0, "trend_down", (" < EMA200" if ema200 is not None else "")
    return (0.3 if price > ema50 else -0.3), "trend_mixed", ""


def _context_direction(context: pd.DataFrame) -> float:
    """Bağlam zaman diliminin yönü: fiyatın EMA50'ye göre konumu."""
    if len(context) < 50:
        return 0.0
    ema50 = _last_float(ind.ema(context["close"], 50))
    if ema50 is None:
        return 0.0
    return math.copysign(1.0, float(context["close"].iloc[-1]) - ema50)


def _context_factor(raw: float, context_score: float) -> tuple[float, str]:
    if context_score == 0.0 or raw == 0.0:
        return 1.0, "trend_context_flat"
    if math.copysign(1.0, raw) == context_score:
        return CONTEXT_SAME, "trend_context_same"
    return CONTEXT_AGAINST, "trend_context_against"


def _momentum(base: pd.DataFrame, atr_value: float) -> Component:
    """RSI (−1..+1'e ölçekli) ve ATR ile normalize MACD histogramı."""
    close = base["close"]
    rsi_value = _last_float(ind.rsi(close, 14))
    if rsi_value is None:
        return Component(0.0)
    rsi_part = (rsi_value - 50.0) / 50.0
    extreme = rsi_value >= RSI_HIGH or rsi_value <= RSI_LOW
    if extreme:
        rsi_part *= 0.5  # aşırı bölgede momentum sönümlenir (dönüş riski)

    histogram = ind.macd(close).histogram
    now = _last_float(histogram)
    if now is None or len(histogram.dropna()) < 4:
        return Component(clip_score(rsi_part), (render("momentum_extreme", rsi=_fmt(rsi_value)),))
    change = now - float(histogram.dropna().iloc[-4])
    macd_part = clip_score(now / atr_value) * 0.5 + clip_score(change / atr_value) * 0.5
    text = render("momentum", rsi=_fmt(rsi_value), macd_tr=_macd_phrase(now, change))
    rationale = (text, render("momentum_extreme", rsi=_fmt(rsi_value))) if extreme else (text,)
    return Component(clip_score(0.6 * rsi_part + 0.4 * macd_part), rationale)


def _macd_phrase(now: float, change: float) -> str:
    side = "pozitif" if now > 0 else "negatif"
    direction = "artıyor" if change > 0 else ("azalıyor" if change < 0 else "yatay")
    return f"{side} ve {direction}"


def _volume(base: pd.DataFrame, price: float) -> Component:
    """Son hareketin hacim onayı + hacim profiline göre konum."""
    if len(base) < VOLUME_SLOW_BARS + VOLUME_FAST_BARS:
        return Component(0.0)
    close = base["close"]
    move = float(close.iloc[-1]) - float(close.iloc[-1 - VOLUME_FAST_BARS])
    direction = math.copysign(1.0, move) if move != 0 else 0.0
    fast = float(base["volume"].tail(VOLUME_FAST_BARS).mean())
    slow = float(base["volume"].tail(VOLUME_SLOW_BARS).mean())
    ratio = fast / slow if slow > 0 else 1.0
    confirmation = direction * clip_score(ratio - 1.0) if not _is_average(ratio) else 0.0
    rationale = [render(_volume_key(ratio), bars=VOLUME_FAST_BARS, ratio=_fmt(ratio, 2))]

    profile_part, profile_text = _profile_position(base, price)
    if profile_text is not None:
        rationale.append(profile_text)
    return Component(clip_score(0.6 * confirmation + 0.4 * profile_part), tuple(rationale))


def _is_average(ratio: float) -> bool:
    """Hacim ortalamadan belirgin sapmıyorsa onay da ret de yoktur."""
    return VOLUME_WEAK_RATIO < ratio < VOLUME_CONFIRM_RATIO


def _volume_key(ratio: float) -> str:
    if _is_average(ratio):
        return "volume_neutral"
    return "volume_confirms" if ratio >= VOLUME_CONFIRM_RATIO else "volume_weak"


def _profile_position(base: pd.DataFrame, price: float) -> tuple[float, str | None]:
    profile = lv.volume_profile(base)
    if profile is None:
        return 0.0, None
    poc = _fmt(profile.poc, 2)
    if price > profile.value_area_high:
        return 0.5, render("volume_above_value", poc=poc)
    if price < profile.value_area_low:
        return -0.5, render("volume_below_value", poc=poc)
    return 0.0, render("volume_inside_value", poc=poc)


def _sr(base: pd.DataFrame, price: float, atr_value: float) -> Component:
    """1 ATR içindeki destek/direnç. Yakın direnç aşağı, yakın destek yukarı yönlüdür."""
    points = lv.swing_points(base)
    levels = lv.cluster_levels(points, tolerance=0.5 * atr_value)
    support, resistance = lv.nearest_levels(levels, price)
    score = 0.0
    rationale: list[str] = []
    if resistance is not None:
        distance = (resistance.price - price) / atr_value
        if distance <= 1.0:
            score -= 1.0 - distance
            rationale.append(
                render(
                    "sr_resistance_near",
                    distance=_fmt(distance, 2),
                    touches=resistance.touches,
                    level=_fmt(resistance.price, 2),
                )
            )
    if support is not None:
        distance = (price - support.price) / atr_value
        if distance <= 1.0:
            score += 1.0 - distance
            rationale.append(
                render(
                    "sr_support_near",
                    distance=_fmt(distance, 2),
                    touches=support.touches,
                    level=_fmt(support.price, 2),
                )
            )
    if not rationale:
        rationale.append(render("sr_clear"))
    return Component(clip_score(score), tuple(rationale))


def _vol_regime(base: pd.DataFrame, interval: Interval) -> Component:
    """Volatilite rejimi: −1 sıkışma, +1 genişleme. Skora değil güvene ve aralığa etki eder."""
    window = _regime_window(base, interval)
    if window < 2:
        return Component(0.0)
    atr_pct = _last_float(ind.percentile_rank(ind.atr(base, 14), window))
    width_pct = _last_float(ind.percentile_rank(ind.bollinger(base["close"], 20).width, window))
    available = [value for value in (atr_pct, width_pct) if value is not None]
    if not available:
        return Component(0.0)
    percentile = sum(available) / len(available)
    if percentile <= SQUEEZE_PCT:
        text = render("vol_squeeze", pct=_fmt(percentile * 100, 0))
    elif percentile >= EXPANSION_PCT:
        text = render("vol_expansion", pct=_fmt(percentile * 100, 0))
    else:
        return Component(percentile * 2 - 1)
    return Component(percentile * 2 - 1, (text,))


def _regime_window(base: pd.DataFrame, interval: Interval) -> int:
    """90 günlük yüzdelik penceresi, eldeki bar sayısıyla sınırlı."""
    wanted = int(REGIME_WINDOW_DAYS * 24 * 3600 / interval.length.total_seconds())
    return max(0, min(wanted, len(base)))


def _coverage(snapshot: FeatureSnapshot, horizon: Horizon) -> float:
    """Ana zaman dilimi ağırlıklı kapsama.

    Bağlam eksikse modül yine çalışabilir (yalnız daha az bilgiyle); bu yüzden `min` değil
    ağırlıklı ortalama kullanılır — aksi halde eksik bağlam "hiç veri yok" gibi görünürdü.
    """
    base = snapshot.coverage_of(horizon.base_interval)
    context = snapshot.coverage_of(horizon.context_interval)
    return BASE_COVERAGE_SHARE * base + (1.0 - BASE_COVERAGE_SHARE) * context


def _confidence(
    snapshot: FeatureSnapshot,
    horizon: Horizon,
    scores: Mapping[str, float],
    *,
    squeeze: bool,
) -> float:
    """kapsama × tazelik × (1 − 0.3·sıkışma) × bileşen uyumu (ARCHITECTURE.md §8.2)."""
    coverage = _coverage(snapshot, horizon)
    freshness = snapshot.freshness_of(horizon.base_interval)
    freshness_factor = 1.0 if freshness <= 1.0 else max(0.0, 1.0 - (freshness - 1.0) / 4.0)
    directional = [scores[name] for name, weight in COMPONENT_WEIGHTS.items() if weight > 0]
    agreement = 1.0 - _spread(directional)
    value = coverage * freshness_factor * (1.0 - 0.3 * squeeze) * agreement
    return max(0.0, min(1.0, value))


def _spread(values: list[float]) -> float:
    """Bileşenlerin dağılımı 0..1: hepsi aynı yöndeyse 0'a, zıtsa 1'e yakın."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return min(1.0, math.sqrt(variance))


def _rationale(parts: Mapping[str, Component]) -> tuple[str, ...]:
    """En güçlü bileşenlerin cümleleri; katkı sırasına göre, en fazla 5 madde."""
    ordered = sorted(
        parts.items(),
        key=lambda item: abs(item[1].score) * COMPONENT_WEIGHTS.get(item[0], 0.0),
        reverse=True,
    )
    lines: list[str] = []
    for _, component in ordered:
        for text in component.rationale:
            if text not in lines:
                lines.append(text)
    return tuple(lines[:MAX_RATIONALE])


def _last_float(series: pd.Series) -> float | None:
    """Serinin son geçerli değeri; hiç yoksa None (NaN sıfır sayılmaz)."""
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[-1])


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}"
