"""Destek/direnç seviyeleri ve hacim profili.

Ayrı dosya: `indicators.py` klasik gösterge hesaplarını tutar, burada fiyat **seviyeleri** üretilir
(ARCHITECTURE.md §8.2'deki `sr` ve `volume` bileşenleri). Öznel çizgi yoktur; seviyeler yalnızca iki
mekanik tanımdan gelir: onaylanmış swing noktaları ve hacim profili.

Nedensellik: bir swing noktası ancak kendisinden sonra `confirm` bar kapandıktan sonra "onaylanmış"
sayılır. Böylece seviye listesi, o anda gerçekten bilinebilecek bilgiden oluşur.
"""

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

SwingKind = Literal["high", "low"]

DEFAULT_CONFIRM: Final = 5
DEFAULT_LOOKBACK: Final = 200
DEFAULT_BINS: Final = 50
VALUE_AREA_SHARE: Final = 0.70


@dataclass(frozen=True)
class SwingPoint:
    ts: pd.Timestamp
    price: float
    kind: SwingKind


@dataclass(frozen=True)
class Level:
    """Kümelenmiş fiyat seviyesi. `touches`: kaç swing noktası bu kümede."""

    price: float
    touches: int
    kind: SwingKind


@dataclass(frozen=True)
class VolumeProfile:
    """Hacim profili: en çok işlem gören fiyat (POC) ve değer alanı."""

    poc: float
    value_area_low: float
    value_area_high: float


def swing_points(
    candles: pd.DataFrame,
    *,
    confirm: int = DEFAULT_CONFIRM,
    lookback: int = DEFAULT_LOOKBACK,
) -> list[SwingPoint]:
    """Onaylanmış swing high/low noktaları (en yenisi sonda).

    Bar `i` swing high'dır: `high[i]` solundaki `confirm` bardan kesin olarak büyük, sağındaki
    `confirm` bardan büyük ya da eşittir. Düz tepe (aynı fiyatın tekrarı) tek seviye üretir.
    Son `confirm` bar onaylanamaz, bu yüzden hiç değerlendirilmez — gelecek bilgisi sızmaz.
    """
    if confirm < 1:
        msg = f"confirm en az 1 olmalı, verilen: {confirm}"
        raise ValueError(msg)
    window = candles.tail(lookback)
    highs = window["high"].to_numpy(dtype="float64")
    lows = window["low"].to_numpy(dtype="float64")
    times = window.index
    points: list[SwingPoint] = []
    for i in range(confirm, len(window) - confirm):
        if _is_pivot(highs, i, confirm, high=True):
            points.append(SwingPoint(ts=times[i], price=float(highs[i]), kind="high"))
        if _is_pivot(lows, i, confirm, high=False):
            points.append(SwingPoint(ts=times[i], price=float(lows[i]), kind="low"))
    return points


def _is_pivot(series: npt.NDArray[np.float64], i: int, confirm: int, *, high: bool) -> bool:
    left = series[i - confirm : i]
    right = series[i + 1 : i + confirm + 1]
    if high:
        return bool((series[i] > left).all() and (series[i] >= right).all())
    return bool((series[i] < left).all() and (series[i] <= right).all())


def cluster_levels(points: list[SwingPoint], tolerance: float) -> list[Level]:
    """Birbirine `tolerance` (0.5×ATR) kadar yakın swing'leri tek seviyede birleştirir.

    Aynı bölgeye üç kez dokunulmuşsa bu tek bir güçlü seviyedir; üç ayrı çizgi değil.
    """
    if tolerance <= 0:
        msg = f"tolerans pozitif olmalı, verilen: {tolerance}"
        raise ValueError(msg)
    levels: list[Level] = []
    for kind in ("high", "low"):
        same_kind = sorted((p for p in points if p.kind == kind), key=lambda p: p.price)
        bucket: list[float] = []
        for point in same_kind:
            if bucket and point.price - bucket[0] > tolerance:
                levels.append(_level_from(bucket, kind))
                bucket = []
            bucket.append(point.price)
        if bucket:
            levels.append(_level_from(bucket, kind))
    return sorted(levels, key=lambda level: level.price)


def nearest_levels(levels: list[Level], price: float) -> tuple[Level | None, Level | None]:
    """Fiyatın altındaki en yakın destek ve üstündeki en yakın direnç."""
    below = [level for level in levels if level.price < price]
    above = [level for level in levels if level.price > price]
    support = max(below, key=lambda level: level.price) if below else None
    resistance = min(above, key=lambda level: level.price) if above else None
    return support, resistance


def volume_profile(candles: pd.DataFrame, *, bins: int = DEFAULT_BINS) -> VolumeProfile | None:
    """Hacim profili. Her mumun hacmi `low..high` aralığına eşit dağıtılır.

    Tipik fiyata tek nokta olarak yazmak, geniş mumlarda hacmi olduğundan dar gösterir.
    Veri yetersizse (tek fiyat seviyesi, hacim yok) `None` döner — uydurma seviye üretilmez.
    """
    if candles.empty or bins < 2:
        return None
    low = float(candles["low"].min())
    high = float(candles["high"].max())
    volumes = candles["volume"].to_numpy(dtype="float64")
    if not np.isfinite(low) or not np.isfinite(high) or high <= low or volumes.sum() <= 0:
        return None
    edges = np.linspace(low, high, bins + 1)
    histogram = _distribute_volume(candles, edges, volumes)
    if histogram.sum() <= 0:
        return None
    centers = (edges[:-1] + edges[1:]) / 2.0
    poc_index = int(np.argmax(histogram))
    low_index, high_index = _value_area(histogram, poc_index)
    return VolumeProfile(
        poc=float(centers[poc_index]),
        value_area_low=float(edges[low_index]),
        value_area_high=float(edges[high_index + 1]),
    )


def _distribute_volume(
    candles: pd.DataFrame,
    edges: npt.NDArray[np.float64],
    volumes: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Her mumun hacmini kestiği kovalara, kesişim uzunluğu oranında dağıtır."""
    histogram = np.zeros(len(edges) - 1, dtype="float64")
    lows = candles["low"].to_numpy(dtype="float64")
    highs = candles["high"].to_numpy(dtype="float64")
    for candle_low, candle_high, volume in zip(lows, highs, volumes, strict=True):
        if volume <= 0:
            continue
        overlap = np.clip(
            np.minimum(edges[1:], candle_high) - np.maximum(edges[:-1], candle_low), 0.0, None
        )
        total = overlap.sum()
        if total <= 0:  # mum tek fiyatta kapandı: hacmi içine düştüğü kovaya yaz
            index = int(np.clip(np.searchsorted(edges, candle_high) - 1, 0, len(histogram) - 1))
            histogram[index] += volume
            continue
        histogram += volume * overlap / total
    return histogram


def _value_area(histogram: npt.NDArray[np.float64], poc_index: int) -> tuple[int, int]:
    """POC'den başlayıp toplam hacmin %70'ine ulaşana dek güçlü komşuyu ekler."""
    target = histogram.sum() * VALUE_AREA_SHARE
    low_index = high_index = poc_index
    covered = histogram[poc_index]
    while covered < target and (low_index > 0 or high_index < len(histogram) - 1):
        below = histogram[low_index - 1] if low_index > 0 else -1.0
        above = histogram[high_index + 1] if high_index < len(histogram) - 1 else -1.0
        if above >= below:
            high_index += 1
            covered += above
        else:
            low_index -= 1
            covered += below
    return low_index, high_index


def _level_from(prices: list[float], kind: SwingKind) -> Level:
    return Level(price=float(np.mean(prices)), touches=len(prices), kind=kind)
