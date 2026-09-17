"""Order flow sinyal modülü (ARCHITECTURE.md §8.3).

Piyasa katılımcılarının **nerede durduğunu** ölçer: funding kalabalığı, açık pozisyon ile fiyatın
birlikte hareketi, likidasyonlar, order book dengesizliği ve agresif alım-satım farkı (CVD).
Bunlar fiyatın dönüşümü değildir; fiyattan çıkarılamayan bilgidir (CLAUDE.md §14.1).

Modül saftır: girdi `FeatureSnapshot`, çıktı `SignalResult`. Veri eksikse ilgili bileşen hesaba
girmez; hepsi eksikse modül "veri yok" der ve ensemble ağırlığını dağıtır.
"""

import math
from collections.abc import Mapping
from datetime import timedelta
from typing import Final

import pandas as pd

from marketpulse.core.types import Horizon
from marketpulse.features.snapshot import FeatureSnapshot
from marketpulse.reporting.templates import render
from marketpulse.signals.base import (
    Component,
    ModuleName,
    SignalResult,
    clip_score,
    no_data,
    weighted_score,
)

COMPONENT_WEIGHTS: Final[Mapping[str, float]] = {
    "funding_dev": 0.20,
    "oi_price": 0.30,
    "liquidations": 0.15,
    "book_imbalance": 0.15,
    "cvd": 0.20,
}

# Ufuk → order flow penceresi (ARCHITECTURE.md §8.1).
WINDOW: Final[Mapping[Horizon, timedelta]] = {
    Horizon.H30M: timedelta(minutes=30),
    Horizon.H1H: timedelta(hours=1),
    Horizon.H4H: timedelta(hours=4),
    Horizon.H24H: timedelta(hours=24),
}

NEUTRAL_Z: Final = 1.0  # |z| < 1 → kalabalık yok, bileşen nötr
Z_SCALE: Final = 3.0  # z / 3 → -1..+1 ölçeği
MIN_DISTRIBUTION: Final = 10  # bu kadar örnek yoksa z-skor anlamsız
BOOK_WINDOW_MIN: Final = 5
BOOK_GAIN: Final = 2.0
WEAK_STATE: Final = 0.5  # pozisyon kapanışı (OI↓) gerçek alım/satımdan zayıf sinyaldir
CAPITULATION_MULTIPLE: Final = 3.0
EPS: Final = 1e-9


class OrderflowModule:
    """`SignalModule` implementasyonu; durum tutmaz."""

    name: ModuleName = "orderflow"

    def compute(self, snapshot: FeatureSnapshot, horizon: Horizon) -> SignalResult:
        window = WINDOW[horizon]
        flow = snapshot.dataset("orderflow_1m")
        parts: dict[str, Component | None] = {
            "funding_dev": _funding(snapshot),
            "oi_price": _oi_price(snapshot, horizon, window),
            "liquidations": _liquidations(flow, snapshot, window),
            "book_imbalance": _book_imbalance(flow, snapshot),
            "cvd": _cvd(flow, snapshot, horizon, window),
        }
        available: dict[str, Component] = {
            name: part for name, part in parts.items() if part is not None
        }
        if not available:
            return no_data(self.name, snapshot.as_of)
        scores = {name: part.score for name, part in available.items()}
        coverage = _coverage(snapshot, window)
        return SignalResult(
            module=self.name,
            score=weighted_score(scores, COMPONENT_WEIGHTS),
            confidence=_confidence(coverage, scores),
            coverage=coverage,
            components=scores,
            rationale=_rationale(available),
            data_as_of=snapshot.as_of,
        )


def _funding(snapshot: FeatureSnapshot) -> Component | None:
    """Funding kalabalığı. Aşırı pozitif funding = long tarafı kalabalık → **ters** sinyal."""
    history = snapshot.dataset("funding")
    current = _current_funding(snapshot)
    if current is None or len(history) < MIN_DISTRIBUTION:
        return None
    rates = _numeric(history, "rate").dropna()
    z = _zscore(current, rates)
    if z is None:
        return None
    if abs(z) < NEUTRAL_Z:
        return Component(0.0, (render("funding_neutral", rate=_pct(current)),))
    score = -clip_score(z / Z_SCALE)
    key = "funding_long_crowded" if z > 0 else "funding_short_crowded"
    return Component(score, (render(key, rate=_pct(current), z=f"{z:+.1f}"),))


def _oi_price(snapshot: FeatureSnapshot, horizon: Horizon, window: timedelta) -> Component | None:
    """Açık pozisyon ve fiyatın birlikte hareketi: dört durum (ARCHITECTURE.md §8.3)."""
    oi = _numeric(snapshot.dataset("open_interest"), "oi").dropna()
    closes = _closes(snapshot, horizon)
    if len(oi) < MIN_DISTRIBUTION or closes is None or closes.empty:
        return None
    oi_steps = max(1, int(window / timedelta(minutes=5)))
    price_steps = max(1, int(window / horizon.base_interval.length))
    oi_changes = oi.pct_change(periods=oi_steps).dropna()
    price_changes = closes.pct_change(periods=price_steps).dropna()
    if len(oi_changes) < MIN_DISTRIBUTION or len(price_changes) < MIN_DISTRIBUTION:
        return None
    oi_change = float(oi_changes.iloc[-1])
    price_change = float(price_changes.iloc[-1])
    z_oi = _zscore(oi_change, oi_changes)
    z_price = _zscore(price_change, price_changes)
    if z_oi is None or z_price is None:
        return None

    # Yön ham değişimden gelir; z yalnızca "bu hareket olağan dışı mı" sorusunu yanıtlar.
    # (z'nin işaretini yön sanmak yanlıştır: yükselen bir seride son değişim ortalamanın
    # altında kalabilir ve z negatif çıkar.)
    magnitude = min(abs(z_oi), abs(z_price)) / Z_SCALE
    rising_oi, rising_price = oi_change > 0, price_change > 0
    if rising_oi and rising_price:
        score, key = magnitude, "oi_real_buying"
    elif rising_oi and not rising_price:
        score, key = -magnitude, "oi_short_building"
    elif not rising_oi and rising_price:
        score, key = magnitude * WEAK_STATE, "oi_short_covering"
    else:
        score, key = -magnitude * WEAK_STATE, "oi_long_unwinding"
    text = render(key, oi_pct=_pct(oi_change), price_pct=_pct(price_change))
    return Component(clip_score(score), (text,))


def _liquidations(
    flow: pd.DataFrame, snapshot: FeatureSnapshot, window: timedelta
) -> Component | None:
    """Net likidasyon yönü; olağandışı büyüklükte ise kapitülasyon sayılıp ters çevrilir."""
    if flow.empty or "liq_long_usd" not in flow:
        return None
    longs = _tail_sum(flow, "liq_long_usd", snapshot.as_of, window)
    shorts = _tail_sum(flow, "liq_short_usd", snapshot.as_of, window)
    total = longs + shorts
    if total <= 0:
        return Component(0.0, (render("liq_quiet"),))
    # Short'lar tasfiye olunca zorunlu ALIM gelir → yukarı; long'lar tasfiye olunca satış → aşağı.
    net = (shorts - longs) / (total + EPS)
    median = _median_window_total(flow, window)
    capitulation = median is not None and total > median * CAPITULATION_MULTIPLE
    score = -net if capitulation else net
    key = "liq_capitulation" if capitulation else ("liq_short" if net > 0 else "liq_long")
    return Component(
        clip_score(score), (render(key, usd=_usd(total), side_usd=_usd(max(longs, shorts))),)
    )


def _book_imbalance(flow: pd.DataFrame, snapshot: FeatureSnapshot) -> Component | None:
    """Top-20 dengesizliğinin 5 dk ortalaması ve ±%1 derinlik dengesizliği, eşit ağırlık."""
    if flow.empty:
        return None
    recent = _tail(flow, snapshot.as_of, timedelta(minutes=BOOK_WINDOW_MIN))
    top20 = _numeric(recent, "top20_imbalance").dropna()
    depth = _numeric(recent, "depth1pct_imbalance").dropna()
    values = [float(series.mean()) for series in (top20, depth) if not series.empty]
    if not values:
        return None
    imbalance = sum(values) / len(values)
    key = "book_bid_heavy" if imbalance > 0 else "book_ask_heavy"
    return Component(
        clip_score(imbalance * BOOK_GAIN), (render(key, pct=_pct(imbalance, digits=0)),)
    )


def _net_flow(
    flow: pd.DataFrame, snapshot: FeatureSnapshot, window: timedelta
) -> tuple[float, float] | None:
    """Pencerede (net agresif akış, toplam hacim). İki kaynak sırayla denenir.

    Birinci kaynak WS `aggTrade` (dakikalık `orderflow_1m`): en ince çözünürlük.
    İkinci kaynak REST `taker_volume` (5 dk ızgarası): ARCHITECTURE §4 bunu zaten "CVD'nin REST
    yedeği" olarak tanımlar. Yedek gerçek bir ihtiyaç: canlıda futures işlem akışının hiç mesaj
    göndermediği ölçüldü (aynı sunucudaki derinlik akışı çalışırken), bileşen bu yüzden tamamen
    kayboluyordu. İkisi de boşsa `None` — o zaman bileşen gerçekten "veri yok"tur.
    """
    for frame, delta_column in ((flow, "cvd_delta"), (snapshot.dataset("taker_volume"), None)):
        if frame.empty:
            continue
        recent = _tail(frame, snapshot.as_of, window)
        buys = _numeric(recent, "buy_vol").fillna(0.0)
        sells = _numeric(recent, "sell_vol").fillna(0.0)
        volume = float((buys + sells).sum())
        if volume <= 0:
            continue
        if delta_column is not None and delta_column in recent:
            net = float(_numeric(recent, delta_column).fillna(0.0).sum())
        else:
            net = float(buys.sum() - sells.sum())
        return net, volume
    return None


def _cvd(
    flow: pd.DataFrame, snapshot: FeatureSnapshot, horizon: Horizon, window: timedelta
) -> Component | None:
    """Agresif alım-satım farkı ve fiyatla uyumu. Uyumsuzluk (divergence) daha güçlü sinyaldir."""
    measured = _net_flow(flow, snapshot, window)
    if measured is None:
        return None
    net, volume = measured
    # Hacme oranlanır: CVD hacim birimindedir, fiyat birimiyle normalize edilemez.
    pressure = net / volume
    price_change = _price_change(snapshot, horizon, window)
    if price_change is None or price_change == 0.0:
        return Component(clip_score(pressure), (render("cvd_flow", pct=_pct(pressure, digits=0)),))

    aligned = math.copysign(1.0, pressure) == math.copysign(1.0, price_change)
    score = clip_score(pressure * WEAK_STATE) if aligned else clip_score(pressure)
    key = "cvd_aligned" if aligned else ("cvd_absorption" if pressure > 0 else "cvd_distribution")
    return Component(score, (render(key, pct=_pct(pressure, digits=0)),))


def _coverage(snapshot: FeatureSnapshot, window: timedelta) -> float:
    """Kapsama: dakikaların gerçekten dinlenmiş saniyesi + türev veri setlerinin varlığı."""
    flow = _tail(snapshot.dataset("orderflow_1m"), snapshot.as_of, window)
    minutes = max(1, int(window / timedelta(minutes=1)))
    if flow.empty:
        listened = 0.0
    else:
        seconds = _numeric(flow, "coverage_seconds").fillna(0.0)
        listened = min(1.0, float(seconds.sum()) / (minutes * 60.0))
    datasets = [
        1.0 if snapshot.has(name) else 0.0 for name in ("funding", "open_interest", "orderflow_1m")
    ]
    return round(0.5 * listened + 0.5 * (sum(datasets) / len(datasets)), 4)


def _confidence(coverage: float, scores: Mapping[str, float]) -> float:
    """kapsama × bileşen uyumu. Bileşenler zıtsa modül kendi içinde çelişiyordur."""
    values = list(scores.values())
    if len(values) < 2:
        return max(0.0, min(1.0, coverage))
    mean = sum(values) / len(values)
    spread = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    return max(0.0, min(1.0, coverage * (1.0 - min(1.0, spread))))


def _rationale(parts: Mapping[str, Component]) -> tuple[str, ...]:
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
    return tuple(lines[:5])


def _current_funding(snapshot: FeatureSnapshot) -> float | None:
    """Anlık funding; canlı satır yoksa son gerçekleşen ödeme."""
    live = snapshot.dataset("funding_live")
    if not live.empty:
        value = _numeric(live, "last_rate").dropna()
        if not value.empty:
            return float(value.iloc[-1])
    history = snapshot.dataset("funding")
    if history.empty:
        return None
    rates = _numeric(history, "rate").dropna()
    return float(rates.iloc[-1]) if not rates.empty else None


def _closes(snapshot: FeatureSnapshot, horizon: Horizon) -> pd.Series | None:
    frame = snapshot.frame(horizon.base_interval)
    if frame.empty:
        return None
    return _numeric(frame, "close").dropna()


def _price_change(snapshot: FeatureSnapshot, horizon: Horizon, window: timedelta) -> float | None:
    closes = _closes(snapshot, horizon)
    steps = max(1, int(window / horizon.base_interval.length))
    if closes is None or len(closes) <= steps:
        return None
    return float(closes.iloc[-1] / closes.iloc[-1 - steps] - 1.0)


def _zscore(value: float, distribution: pd.Series) -> float | None:
    if len(distribution) < MIN_DISTRIBUTION:
        return None
    std = float(distribution.std(ddof=0))
    if std <= 0:
        return None
    return (value - float(distribution.mean())) / std


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    """Sütunu sayısal seriye çevirir; sütun yoksa boş seri (KeyError yerine "veri yok")."""
    if column not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _tail(frame: pd.DataFrame, as_of: pd.Timestamp | object, window: timedelta) -> pd.DataFrame:
    if frame.empty:
        return frame
    cutoff = pd.Timestamp(as_of) - window  # type: ignore[arg-type]
    return frame[frame.index > cutoff]


def _tail_sum(
    frame: pd.DataFrame, column: str, as_of: pd.Timestamp | object, window: timedelta
) -> float:
    return float(_numeric(_tail(frame, as_of, window), column).fillna(0.0).sum())


def _median_window_total(frame: pd.DataFrame, window: timedelta) -> float | None:
    """Son 24 saatteki pencere toplamlarının medyanı: "olağan" likidasyon büyüklüğü."""
    minutes = max(1, int(window / timedelta(minutes=1)))
    total = _numeric(frame, "liq_long_usd").fillna(0.0) + _numeric(frame, "liq_short_usd").fillna(
        0.0
    )
    if len(total) < minutes * 2:
        return None
    rolled = total.rolling(window=minutes, min_periods=minutes).sum().dropna()
    median = float(rolled.median())
    return median if median > 0 else None


def _pct(value: float, digits: int = 3) -> str:
    return f"%{value * 100:.{digits}f}"


def _usd(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M$"
    if value >= 1_000:
        return f"{value / 1_000:.0f}B$"
    return f"{value:.0f}$"
