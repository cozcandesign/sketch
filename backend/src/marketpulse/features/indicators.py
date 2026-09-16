"""Teknik göstergeler (K13: kendi implementasyonumuz, pandas-ta / TA-Lib yok).

Hepsi **nedenseldir**: `çıktı[i]` yalnızca `girdi[:i+1]`'e bağlıdır (CLAUDE.md §9.4). Merkezlenmiş
pencere, negatif `shift` ve ileri doldurma sonrası geri bakış kullanılmaz. Yetersiz veri `NaN`
verir; çağıran taraf `NaN`'ı "veri yok" olarak ele alır, sıfır saymaz.

Sözleşme: girdi `pd.Series` (float) veya OHLCV `pd.DataFrame`; çıktı aynı indeksli `pd.Series`.
"""

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

HIGH: Final = "high"
LOW: Final = "low"
CLOSE: Final = "close"


@dataclass(frozen=True)
class MacdResult:
    macd: pd.Series
    signal: pd.Series
    histogram: pd.Series


@dataclass(frozen=True)
class BollingerResult:
    middle: pd.Series
    upper: pd.Series
    lower: pd.Series
    width: pd.Series  # (upper - lower) / middle, oransal genişlik


@dataclass(frozen=True)
class AdxResult:
    adx: pd.Series
    plus_di: pd.Series
    minus_di: pd.Series


def sma(values: pd.Series, period: int) -> pd.Series:
    """Basit hareketli ortalama. İlk `period-1` değer NaN."""
    _require_period(period)
    return values.rolling(window=period, min_periods=period).mean()


def ema(values: pd.Series, period: int) -> pd.Series:
    """Üstel hareketli ortalama; tohum = ilk tam pencerenin SMA'sı (TradingView sözleşmesi).

    `ewm(adjust=False)` ilk değeri tohum alır ve serinin başına aşırı duyarlıdır; SMA tohumu
    referans değerlerle karşılaştırmayı da kolaylaştırır.
    """
    _require_period(period)
    if len(values) < period:
        return pd.Series(np.nan, index=values.index, dtype="float64")
    seeded = values.copy().astype("float64")
    seed = float(values.iloc[:period].mean())
    seeded.iloc[period - 1] = seed
    smoothed = seeded.iloc[period - 1 :].ewm(span=period, adjust=False).mean()
    return _left_pad(smoothed, values.index, period)


def rma(values: pd.Series, period: int) -> pd.Series:
    """Wilder yumuşatması (RSI, ATR, ADX'in kullandığı ortalama): alfa = 1/period."""
    _require_period(period)
    if len(values) < period:
        return pd.Series(np.nan, index=values.index, dtype="float64")
    seeded = values.copy().astype("float64")
    seeded.iloc[period - 1] = float(values.iloc[:period].mean())
    smoothed = seeded.iloc[period - 1 :].ewm(alpha=1.0 / period, adjust=False).mean()
    return _left_pad(smoothed, values.index, period)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI, 0..100. Sabit seride 100 değil 50 döner (bölme sıfır → nötr)."""
    _require_period(period)
    delta = close.astype("float64").diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = rma(gain.iloc[1:], period)
    avg_loss = rma(loss.iloc[1:], period)
    rs_up = avg_gain.reindex(close.index)
    rs_down = avg_loss.reindex(close.index)
    total = rs_up + rs_down
    value = np.where(total > 0, 100.0 * rs_up / total, 50.0)
    result = pd.Series(value, index=close.index, dtype="float64")
    return result.where(total.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> MacdResult:
    """MACD çizgisi, sinyal çizgisi ve histogram (fiyat birimiyle)."""
    line = ema(close, fast) - ema(close, slow)
    signal_line = ema(line.dropna(), signal).reindex(close.index)
    return MacdResult(macd=line, signal=signal_line, histogram=line - signal_line)


def true_range(candles: pd.DataFrame) -> pd.Series:
    """Gerçek aralık: max(H−L, |H−önceki C|, |L−önceki C|). İlk bar H−L."""
    high = candles[HIGH].astype("float64")
    low = candles[LOW].astype("float64")
    prev_close = candles[CLOSE].astype("float64").shift(1)
    ranges = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1)
    return ranges.max(axis=1, skipna=True)


def atr(candles: pd.DataFrame, period: int = 14) -> pd.Series:
    """Ortalama gerçek aralık (Wilder). Fiyat birimiyle."""
    return rma(true_range(candles), period)


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> BollingerResult:
    """Bollinger bantları; `width` = (üst − alt) / orta, volatilite sıkışması için oransal."""
    _require_period(period)
    middle = sma(close, period)
    # ddof=0: pencere popülasyonun kendisi, örneklem değil (standart Bollinger tanımı).
    deviation = close.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + num_std * deviation
    lower = middle - num_std * deviation
    return BollingerResult(middle=middle, upper=upper, lower=lower, width=(upper - lower) / middle)


def adx(candles: pd.DataFrame, period: int = 14) -> AdxResult:
    """Wilder ADX ve yönlü göstergeler (+DI, −DI), 0..100."""
    _require_period(period)
    high = candles[HIGH].astype("float64")
    low = candles[LOW].astype("float64")
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=candles.index,
        dtype="float64",
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=candles.index,
        dtype="float64",
    )
    smoothed_tr = rma(true_range(candles).iloc[1:], period).reindex(candles.index)
    plus_di = 100.0 * rma(plus_dm.iloc[1:], period).reindex(candles.index) / smoothed_tr
    minus_di = 100.0 * rma(minus_dm.iloc[1:], period).reindex(candles.index) / smoothed_tr
    di_sum = plus_di + minus_di
    dx = pd.Series(
        np.where(di_sum > 0, 100.0 * (plus_di - minus_di).abs() / di_sum, 0.0),
        index=candles.index,
        dtype="float64",
    ).where(di_sum.notna())
    return AdxResult(
        adx=rma(dx.dropna(), period).reindex(candles.index),
        plus_di=plus_di,
        minus_di=minus_di,
    )


def percentile_rank(values: pd.Series, window: int) -> pd.Series:
    """Son değerin kendi `window` uzunluğundaki geçmişi içindeki yüzdelik sırası (0..1).

    Volatilite rejimi için: ATR'nin mutlak değeri sembolden sembole değişir, yüzdelik sırası
    karşılaştırılabilir. Nedensel: yalnızca geçmiş pencereye bakar.
    """
    _require_period(window)

    def rank(window_values: npt.NDArray[np.float64]) -> float:
        last = window_values[-1]
        if np.isnan(last):
            return float("nan")
        history = window_values[:-1]
        history = history[~np.isnan(history)]
        if history.size == 0:
            return float("nan")
        return float((history <= last).mean())

    return values.rolling(window=window, min_periods=2).apply(rank, raw=True)


def _left_pad(values: pd.Series, index: pd.Index, period: int) -> pd.Series:
    """Yumuşatılmış seriyi orijinal indekse oturtur; ilk `period-1` yer NaN kalır."""
    padded = np.full(len(index), np.nan, dtype="float64")
    padded[period - 1 :] = values.to_numpy(dtype="float64")
    return pd.Series(padded, index=index, dtype="float64")


def _require_period(period: int) -> None:
    if period < 1:
        msg = f"periyot en az 1 olmalı, verilen: {period}"
        raise ValueError(msg)
