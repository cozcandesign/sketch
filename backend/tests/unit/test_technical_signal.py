"""Teknik modül testleri (CLAUDE.md §8: işaret, aralık, eksik veri, yasak kelime)."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from marketpulse.core.types import Horizon, Interval
from marketpulse.features.snapshot import FeatureSnapshot, coverage_key, empty_frame
from marketpulse.reporting.banned_words import find_banned
from marketpulse.signals.technical import COMPONENT_WEIGHTS, TechnicalModule

AS_OF = datetime(2026, 3, 1, tzinfo=UTC)
HORIZON = Horizon.H1H  # ana TF 15m, bağlam 1h


def frame_from(
    prices: list[float], interval: Interval, *, volumes: list[float] | None = None
) -> pd.DataFrame:
    if not prices:
        return empty_frame()
    count = len(prices)
    close_times = [AS_OF - (count - 1 - i) * interval.length for i in range(count)]
    close = pd.Series(prices, dtype="float64")
    return pd.DataFrame(
        {
            "open_time": [t - interval.length for t in close_times],
            "open": close.shift(1).fillna(close.iloc[0]).to_numpy(),
            "high": (close * 1.003).to_numpy(),
            "low": (close * 0.997).to_numpy(),
            "close": close.to_numpy(),
            "volume": volumes if volumes is not None else [100.0] * count,
            "quote_volume": [1000.0] * count,
            "trades": [10] * count,
            "taker_buy_base": [50.0] * count,
        },
        index=pd.DatetimeIndex(close_times, name="close_time"),
    )


def snapshot_from(
    base_prices: list[float],
    context_prices: list[float] | None = None,
    *,
    volumes: list[float] | None = None,
    coverage: float = 1.0,
    freshness: float = 0.0,
) -> FeatureSnapshot:
    base_tf, context_tf = HORIZON.base_interval, HORIZON.context_interval
    candles = {base_tf: frame_from(base_prices, base_tf, volumes=volumes)}
    if context_prices is not None:
        candles[context_tf] = frame_from(context_prices, context_tf)
    return FeatureSnapshot(
        symbol="BTCUSDT",
        as_of=AS_OF,
        candles=candles,
        coverage={coverage_key(tf): coverage for tf in (base_tf, context_tf)},
        freshness={coverage_key(tf): freshness for tf in (base_tf, context_tf)},
        price=base_prices[-1] if base_prices else None,
    )


def rising(count: int = 260, step: float = 0.4, start: float = 100.0) -> list[float]:
    return [start + step * i for i in range(count)]


def falling(count: int = 260, step: float = 0.4, start: float = 200.0) -> list[float]:
    return [start - step * i for i in range(count)]


def noisy(count: int = 260, seed: int = 3) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(100.0 + np.cumsum(rng.normal(0, 0.3, count)))


def test_a_clean_uptrend_scores_positive() -> None:
    result = TechnicalModule().compute(snapshot_from(rising(), rising(120)), HORIZON)
    assert result.score > 0.3
    assert result.components["trend"] > 0
    assert result.coverage == pytest.approx(1.0)


def test_a_clean_downtrend_scores_negative() -> None:
    result = TechnicalModule().compute(snapshot_from(falling(), falling(120)), HORIZON)
    assert result.score < -0.3
    assert result.components["trend"] < 0


def test_the_score_and_every_component_stay_inside_minus_one_to_plus_one() -> None:
    for prices in (rising(), falling(), noisy()):
        result = TechnicalModule().compute(snapshot_from(prices, prices[:120]), HORIZON)
        assert -1.0 <= result.score <= 1.0
        for name, value in result.components.items():
            assert -1.0 <= value <= 1.0, name


def test_a_context_timeframe_pointing_the_other_way_dampens_the_trend() -> None:
    """Aynı ana TF, farklı bağlam: ters bağlam skoru küçültmeli (×0.6 vs ×1.2)."""
    same = TechnicalModule().compute(snapshot_from(rising(), rising(120)), HORIZON)
    against = TechnicalModule().compute(snapshot_from(rising(), falling(120)), HORIZON)
    assert against.components["trend"] < same.components["trend"]


def test_missing_candles_mean_no_data_not_a_crash() -> None:
    result = TechnicalModule().compute(snapshot_from([], None), HORIZON)
    assert result.coverage == 0.0
    assert not result.has_data
    assert result.score == 0.0


def test_too_few_bars_mean_no_data() -> None:
    result = TechnicalModule().compute(snapshot_from(rising(30)), HORIZON)
    assert not result.has_data


def test_a_missing_context_timeframe_lowers_coverage_but_still_scores() -> None:
    snapshot = snapshot_from(rising(), None)
    snapshot = FeatureSnapshot(
        symbol=snapshot.symbol,
        as_of=snapshot.as_of,
        candles=snapshot.candles,
        coverage={coverage_key(HORIZON.base_interval): 1.0},
        freshness={coverage_key(HORIZON.base_interval): 0.0},
        price=snapshot.price,
    )
    result = TechnicalModule().compute(snapshot, HORIZON)
    assert result.coverage == pytest.approx(0.75)  # ana TF var, bağlam yok
    assert result.has_data
    assert result.score != 0.0


def test_stale_candles_reduce_confidence() -> None:
    fresh = TechnicalModule().compute(snapshot_from(rising(), rising(120)), HORIZON)
    stale = TechnicalModule().compute(snapshot_from(rising(), rising(120), freshness=3.0), HORIZON)
    assert stale.confidence < fresh.confidence


def test_partial_coverage_reduces_confidence() -> None:
    full = TechnicalModule().compute(snapshot_from(rising(), rising(120)), HORIZON)
    partial = TechnicalModule().compute(snapshot_from(rising(), rising(120), coverage=0.4), HORIZON)
    assert partial.confidence < full.confidence
    assert partial.coverage == pytest.approx(0.4)


def test_average_volume_neither_confirms_nor_denies_the_move() -> None:
    """Hacim ortalamadayken "destekli" denmez; sabit hacimli seride yanlış onay çıkmamalı."""
    prices = rising()
    snapshot = snapshot_from(prices, volumes=[100.0] * len(prices))
    result = TechnicalModule().compute(snapshot, HORIZON)
    assert any("ortalaması düzeyinde" in line for line in result.rationale)


def test_volume_confirmation_moves_the_volume_component() -> None:
    prices = rising()
    quiet = [100.0] * len(prices)
    loud = [100.0] * (len(prices) - 5) + [400.0] * 5
    quiet_result = TechnicalModule().compute(snapshot_from(prices, volumes=quiet), HORIZON)
    loud_result = TechnicalModule().compute(snapshot_from(prices, volumes=loud), HORIZON)
    assert loud_result.components["volume"] > quiet_result.components["volume"]


def test_volatility_regime_is_reported_but_carries_no_direction() -> None:
    result = TechnicalModule().compute(snapshot_from(noisy(), noisy(120)), HORIZON)
    assert "vol_regime" in result.components
    assert COMPONENT_WEIGHTS["vol_regime"] == 0.0


def test_rationale_is_written_in_turkish_and_free_of_banned_words() -> None:
    for prices in (rising(), falling(), noisy()):
        result = TechnicalModule().compute(snapshot_from(prices, prices[:120]), HORIZON)
        assert result.rationale
        for line in result.rationale:
            assert find_banned(line) == [], line


def test_the_module_is_pure_same_snapshot_same_result() -> None:
    snapshot = snapshot_from(noisy(), noisy(120))
    module = TechnicalModule()
    assert module.compute(snapshot, HORIZON) == module.compute(snapshot, HORIZON)


@pytest.mark.parametrize("horizon", list(Horizon))
def test_every_horizon_produces_a_result(horizon: Horizon) -> None:
    base_tf, context_tf = horizon.base_interval, horizon.context_interval
    candles = {
        base_tf: frame_from(rising(), base_tf),
        context_tf: frame_from(rising(120), context_tf),
    }
    snapshot = FeatureSnapshot(
        symbol="BTCUSDT",
        as_of=AS_OF,
        candles=candles,
        coverage={coverage_key(tf): 1.0 for tf in (base_tf, context_tf)},
        freshness={coverage_key(tf): 0.0 for tf in (base_tf, context_tf)},
        price=rising()[-1],
    )
    result = TechnicalModule().compute(snapshot, horizon)
    assert result.has_data
    assert result.data_as_of == AS_OF
