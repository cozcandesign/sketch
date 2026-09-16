"""Swing noktaları, seviye kümeleme ve hacim profili testleri."""

import numpy as np
import pandas as pd
import pytest

from marketpulse.features import levels as lv


def candles_from(prices: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(prices), freq="5min", tz="UTC")
    close = pd.Series(prices, index=index, dtype="float64")
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": volumes if volumes is not None else [10.0] * len(prices),
        },
        index=index,
    )


def test_swing_high_and_low_are_found_at_the_turning_points() -> None:
    prices = [1.0, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3, 4, 5]
    points = lv.swing_points(candles_from(prices), confirm=2)
    assert [(p.kind, p.price) for p in points] == [("high", 5.5), ("low", 0.5)]


def test_the_last_bars_are_never_confirmed_as_swings() -> None:
    """Son `confirm` bar gelecekte onaylanacak; bugün onaylanmış sayılamaz."""
    rising_then_peak = [1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    points = lv.swing_points(candles_from(rising_then_peak), confirm=3)
    assert points == []  # tepe serinin sonunda: henüz onaylanmadı


def test_a_flat_top_produces_a_single_swing_not_two() -> None:
    prices = [1.0, 2, 3, 5, 5, 3, 2, 1, 2, 3]
    highs = [p for p in lv.swing_points(candles_from(prices), confirm=2) if p.kind == "high"]
    assert len(highs) == 1


def test_nearby_swings_merge_into_one_level_with_touch_count() -> None:
    points = [
        lv.SwingPoint(ts=pd.Timestamp("2026-01-01", tz="UTC"), price=100.0, kind="high"),
        lv.SwingPoint(ts=pd.Timestamp("2026-01-02", tz="UTC"), price=100.4, kind="high"),
        lv.SwingPoint(ts=pd.Timestamp("2026-01-03", tz="UTC"), price=110.0, kind="high"),
    ]
    levels = lv.cluster_levels(points, tolerance=1.0)
    assert [(level.price, level.touches) for level in levels] == [(100.2, 2), (110.0, 1)]


def test_supports_and_resistances_are_the_closest_levels_on_each_side() -> None:
    levels = [
        lv.Level(price=95.0, touches=1, kind="low"),
        lv.Level(price=99.0, touches=2, kind="low"),
        lv.Level(price=104.0, touches=3, kind="high"),
    ]
    support, resistance = lv.nearest_levels(levels, price=100.0)
    assert support is not None
    assert resistance is not None
    assert support.price == 99.0
    assert resistance.price == 104.0


def test_cluster_tolerance_must_be_positive() -> None:
    with pytest.raises(ValueError, match="tolerans"):
        lv.cluster_levels([], tolerance=0.0)


def test_volume_profile_poc_sits_where_the_volume_traded() -> None:
    prices = [100.0] * 5 + [110.0] * 20 + [120.0] * 5
    profile = lv.volume_profile(candles_from(prices), bins=20)
    assert profile is not None
    assert profile.poc == pytest.approx(110.0, abs=0.7)
    assert profile.value_area_low < 110.0 < profile.value_area_high


def test_volume_profile_returns_none_without_usable_data() -> None:
    flat = candles_from([100.0] * 5, volumes=[0.0] * 5)
    assert lv.volume_profile(flat) is None
    assert lv.volume_profile(pd.DataFrame(columns=["high", "low", "volume"])) is None


def test_volume_profile_spreads_each_candle_across_the_bars_it_covers() -> None:
    """Geniş mumun hacmi tek noktaya değil, kapsadığı fiyat aralığına dağıtılır."""
    index = pd.date_range("2026-01-01", periods=2, freq="5min", tz="UTC")
    wide = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [110.0, 101.0],
            "low": [100.0, 100.0],
            "close": [105.0, 100.5],
            "volume": [100.0, 1.0],
        },
        index=index,
    )
    profile = lv.volume_profile(wide, bins=10)
    assert profile is not None
    assert profile.value_area_high > 105.0  # geniş mum üst bölgeyi de doldurur
    assert np.isfinite(profile.poc)
