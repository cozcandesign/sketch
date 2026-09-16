"""Gösterge referans değer testleri (CLAUDE.md §8: elle hesaplanmış küçük seriler).

Beklenen değerler burada açıkça yazılır; "kütüphane ne derse o" testi değildir.
"""

import math

import numpy as np
import pandas as pd
import pytest

from marketpulse.features import indicators as ind


def series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype="float64")


def test_sma_is_the_plain_window_mean() -> None:
    values = series([1, 2, 3, 4, 5])
    result = ind.sma(values, 3)
    assert math.isnan(result.iloc[0])
    assert math.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)  # (1+2+3)/3
    assert result.iloc[4] == pytest.approx(4.0)  # (3+4+5)/3


def test_ema_seeds_with_the_sma_then_applies_the_smoothing_factor() -> None:
    # period=3 → alfa = 2/(3+1) = 0.5. Tohum = (1+2+3)/3 = 2.0
    # i=3: 0.5*4 + 0.5*2.0 = 3.0 ; i=4: 0.5*5 + 0.5*3.0 = 4.0
    result = ind.ema(series([1, 2, 3, 4, 5]), 3)
    assert math.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[3] == pytest.approx(3.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_ema_returns_all_nan_when_the_series_is_shorter_than_the_period() -> None:
    assert ind.ema(series([1, 2]), 5).isna().all()


def test_rma_uses_wilder_alpha() -> None:
    # period=4 → alfa = 0.25. Tohum = (2+4+6+8)/4 = 5.0
    # i=4: 0.25*10 + 0.75*5.0 = 6.25
    result = ind.rma(series([2, 4, 6, 8, 10]), 4)
    assert result.iloc[3] == pytest.approx(5.0)
    assert result.iloc[4] == pytest.approx(6.25)


def test_rsi_is_100_for_a_pure_uptrend_and_0_for_a_pure_downtrend() -> None:
    up = series([float(i) for i in range(1, 30)])
    assert ind.rsi(up, 14).iloc[-1] == pytest.approx(100.0)
    down = series([float(i) for i in range(30, 1, -1)])
    assert ind.rsi(down, 14).iloc[-1] == pytest.approx(0.0)


def test_rsi_is_neutral_on_a_flat_series() -> None:
    """Sabit fiyatta kazanç ve kayıp sıfırdır; 100 değil 50 (nötr) dönmeli."""
    flat = series([100.0] * 30)
    assert ind.rsi(flat, 14).iloc[-1] == pytest.approx(50.0)


def test_rsi_reference_value_on_a_hand_checked_series() -> None:
    # 14 periyot, tek düşüş barı: 13 kazanç (+1), 1 kayıp (−2)
    values = [100.0]
    for step in [1] * 13 + [-2] + [1]:
        values.append(values[-1] + step)
    result = ind.rsi(series(values), 14)
    # Tohum: ortalama kazanç 13/14, ortalama kayıp 2/14 → RSI = 100*13/15 = 86.667
    assert result.iloc[14] == pytest.approx(100.0 * 13.0 / 15.0, abs=1e-6)


def test_macd_histogram_is_macd_minus_signal() -> None:
    values = series([float(v) for v in np.linspace(100, 140, 60)])
    result = ind.macd(values)
    assert result.histogram.iloc[-1] == pytest.approx(result.macd.iloc[-1] - result.signal.iloc[-1])
    assert result.macd.iloc[-1] > 0  # yükselen seride hızlı EMA yavaşın üstünde


def test_true_range_uses_the_previous_close() -> None:
    candles = pd.DataFrame({"high": [10.0, 12.0], "low": [9.0, 11.5], "close": [9.5, 11.8]})
    result = ind.true_range(candles)
    assert result.iloc[0] == pytest.approx(1.0)  # ilk bar: 10 − 9
    assert result.iloc[1] == pytest.approx(2.5)  # |12 − 9.5| boşluk dahil


def test_atr_equals_the_bar_range_when_every_bar_has_the_same_range() -> None:
    close = series([float(v) for v in range(100, 130)])
    candles = pd.DataFrame({"high": close + 1.0, "low": close - 1.0, "close": close})
    assert ind.atr(candles, 14).iloc[-1] == pytest.approx(2.0)


def test_bollinger_bands_sit_two_population_sigmas_from_the_mean() -> None:
    values = series([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    result = ind.bollinger(values, period=8, num_std=2.0)
    assert result.middle.iloc[-1] == pytest.approx(5.0)
    assert result.upper.iloc[-1] == pytest.approx(9.0)  # sigma = 2 (ddof=0)
    assert result.lower.iloc[-1] == pytest.approx(1.0)
    assert result.width.iloc[-1] == pytest.approx(8.0 / 5.0)


def test_adx_is_high_in_a_clean_trend_and_plus_di_leads() -> None:
    close = series([float(v) for v in range(100, 140)])
    candles = pd.DataFrame({"high": close + 1.0, "low": close - 1.0, "close": close})
    result = ind.adx(candles, 14)
    assert result.adx.iloc[-1] > 50.0
    assert result.plus_di.iloc[-1] > result.minus_di.iloc[-1]


def test_percentile_rank_reports_where_the_last_value_sits_in_its_own_history() -> None:
    values = series([1.0, 2.0, 3.0, 4.0, 10.0])
    ranks = ind.percentile_rank(values, 5)
    assert ranks.iloc[-1] == pytest.approx(1.0)  # en yüksek değer
    falling = series([10.0, 4.0, 3.0, 2.0, 1.0])
    assert ind.percentile_rank(falling, 5).iloc[-1] == pytest.approx(0.0)


@pytest.mark.parametrize("period", [0, -1])
def test_indicators_reject_a_non_positive_period(period: int) -> None:
    with pytest.raises(ValueError, match="periyot"):
        ind.sma(series([1.0, 2.0]), period)
