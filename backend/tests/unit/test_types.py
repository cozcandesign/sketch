from datetime import timedelta

import pytest

from marketpulse.core.types import Horizon, parse_symbol


def test_horizon_lengths_and_cadences() -> None:
    assert Horizon.H30M.length == timedelta(minutes=30)
    assert Horizon.H30M.cadence == timedelta(minutes=15)
    assert Horizon.H24H.length == timedelta(hours=24)
    assert Horizon.H24H.cadence == timedelta(hours=4)
    for h in Horizon:
        assert h.cadence <= h.length


def test_horizon_string_values_are_stable() -> None:
    assert [h.value for h in Horizon] == ["30m", "1h", "4h", "24h"]
    assert Horizon("4h") is Horizon.H4H


@pytest.mark.parametrize("raw", ["btcusdt", " ETHUSDT ", "SOLUSDT"])
def test_parse_symbol_normalizes(raw: str) -> None:
    assert parse_symbol(raw) == raw.strip().upper()


@pytest.mark.parametrize("raw", ["", "BTC-USDT", "btc usdt", "X"])
def test_parse_symbol_rejects_bad_format(raw: str) -> None:
    with pytest.raises(ValueError, match="geçersiz sembol"):
        parse_symbol(raw)
