"""Gösterge nedenselliği: `çıktı[i]` yalnızca `girdi[:i+1]`'e bağlıdır (CLAUDE.md §9.4).

Yöntem (gelecek perturbasyonu): seri ikiye ayrılır, ikinci yarı rastgele değiştirilir; ilk yarının
gösterge değerleri **birebir** aynı kalmalıdır. Merkezlenmiş pencere ya da `shift(-n)` kullanan bir
gösterge bu testte anında düşer.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from marketpulse.features import indicators as ind
from marketpulse.features import levels as lv

PRICES = st.lists(
    st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False),
    min_size=60,
    max_size=120,
)
FUTURE = st.lists(
    st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=40,
)

SERIES_INDICATORS: dict[str, Callable[[pd.Series], pd.Series]] = {
    "sma": lambda s: ind.sma(s, 10),
    "ema": lambda s: ind.ema(s, 10),
    "rma": lambda s: ind.rma(s, 10),
    "rsi": lambda s: ind.rsi(s, 14),
    "macd": lambda s: ind.macd(s).histogram,
    "bollinger_width": lambda s: ind.bollinger(s, 20).width,
    "percentile_rank": lambda s: ind.percentile_rank(s, 20),
}

FRAME_INDICATORS: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "true_range": ind.true_range,
    "atr": lambda df: ind.atr(df, 14),
    "adx": lambda df: ind.adx(df, 14).adx,
    "plus_di": lambda df: ind.adx(df, 14).plus_di,
}


def as_candles(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(prices), freq="5min", tz="UTC")
    close = pd.Series(prices, index=index, dtype="float64")
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": np.full(len(prices), 5.0),
        },
        index=index,
    )


@pytest.mark.parametrize("name", sorted(SERIES_INDICATORS))
@given(past=PRICES, future=FUTURE)
@settings(max_examples=25, deadline=None)
def test_series_indicators_ignore_the_future(
    name: str, past: list[float], future: list[float]
) -> None:
    function = SERIES_INDICATORS[name]
    known = pd.Series(past, dtype="float64")
    extended = pd.Series(past + future, dtype="float64")
    on_known = function(known)
    on_extended = function(extended).iloc[: len(past)]
    assert np.allclose(on_known.to_numpy(), on_extended.to_numpy(), equal_nan=True)


@pytest.mark.parametrize("name", sorted(FRAME_INDICATORS))
@given(past=PRICES, future=FUTURE)
@settings(max_examples=25, deadline=None)
def test_frame_indicators_ignore_the_future(
    name: str, past: list[float], future: list[float]
) -> None:
    function = FRAME_INDICATORS[name]
    on_known = function(as_candles(past))
    on_extended = function(as_candles(past + future)).iloc[: len(past)]
    assert np.allclose(on_known.to_numpy(), on_extended.to_numpy(), equal_nan=True)


@given(past=PRICES, future=FUTURE)
@settings(max_examples=25, deadline=None)
def test_confirmed_swings_do_not_change_when_the_future_arrives(
    past: list[float], future: list[float]
) -> None:
    """Onaylanmış swing'ler kalıcıdır: yeni barlar gelince geçmiş seviyeler oynamamalı."""
    confirm = 3
    known = lv.swing_points(as_candles(past), confirm=confirm, lookback=len(past))
    extended = lv.swing_points(
        as_candles(past + future), confirm=confirm, lookback=len(past) + len(future)
    )
    confirmed_later = {(p.ts, p.kind, p.price) for p in extended}
    assert {(p.ts, p.kind, p.price) for p in known} <= confirmed_later
