"""Order flow dakika kovaları: hacim yönü, likidasyon, kitap ortalaması, kapsama süresi."""

from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.collectors.orderflow_agg import OrderflowAggregator
from marketpulse.storage.models import Liquidation

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"


def liquidation(side: str, usd: float, ts: datetime = T0) -> Liquidation:
    return Liquidation(
        symbol=SYMBOL,
        ts=ts,
        side="long" if side == "long" else "short",
        qty=usd / 60000.0,
        price=60000.0,
        usd=usd,
    )


def test_buyer_maker_trades_count_as_selling_pressure() -> None:
    """aggTrade'de `m=true` alıcının maker olduğunu söyler: saldırgan taraf satıcıdır."""
    agg = OrderflowAggregator()
    agg.add_trade(SYMBOL, T0, qty=2.0, is_buyer_maker=False)  # agresif alım
    agg.add_trade(SYMBOL, T0 + timedelta(seconds=5), qty=0.5, is_buyer_maker=True)  # agresif satış

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.buy_vol == pytest.approx(2.0)
    assert row.sell_vol == pytest.approx(0.5)
    assert row.cvd_delta == pytest.approx(1.5)
    assert row.trade_count == 2


def test_liquidations_are_split_by_the_side_that_was_closed() -> None:
    agg = OrderflowAggregator()
    agg.add_liquidation(liquidation("long", 120_000))
    agg.add_liquidation(liquidation("short", 45_000))

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.liq_long_usd == pytest.approx(120_000)
    assert row.liq_short_usd == pytest.approx(45_000)
    assert row.liq_count == 2


def test_book_samples_are_averaged_over_the_minute() -> None:
    agg = OrderflowAggregator()
    agg.add_book(SYMBOL, T0, bids=[(100.0, 3.0)], asks=[(101.0, 1.0)])
    agg.add_book(SYMBOL, T0 + timedelta(seconds=30), bids=[(100.0, 1.0)], asks=[(101.0, 3.0)])

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.top20_bid_qty == pytest.approx(2.0)
    assert row.top20_ask_qty == pytest.approx(2.0)
    assert row.top20_imbalance == pytest.approx(0.0)  # dengede
    assert row.spread_bps == pytest.approx(1.0 / 100.5 * 10_000, rel=1e-6)


def test_a_one_sided_book_reports_the_imbalance_with_its_sign() -> None:
    agg = OrderflowAggregator()
    agg.add_book(SYMBOL, T0, bids=[(100.0, 9.0)], asks=[(101.0, 1.0)])

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.top20_imbalance == pytest.approx(0.8)


def test_a_minute_that_is_still_open_is_never_written() -> None:
    """Yarım dakika yazılırsa hacim olduğundan düşük görünür; kova kapanana kadar bekler."""
    agg = OrderflowAggregator()
    agg.add_trade(SYMBOL, T0 + timedelta(seconds=10), qty=1.0, is_buyer_maker=False)

    assert agg.take_closed(T0 + timedelta(seconds=45)) == []
    assert agg.open_minutes() == 1
    assert len(agg.take_closed(T0 + timedelta(minutes=1))) == 1


def test_coverage_counts_only_the_seconds_the_connection_was_open() -> None:
    agg = OrderflowAggregator()
    agg.mark_connected(T0 + timedelta(seconds=20))
    agg.add_trade(SYMBOL, T0 + timedelta(seconds=25), qty=1.0, is_buyer_maker=False)

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.coverage_seconds == pytest.approx(40.0)


def test_a_disconnect_stops_the_coverage_clock() -> None:
    agg = OrderflowAggregator()
    agg.mark_connected(T0)
    agg.add_trade(SYMBOL, T0 + timedelta(seconds=5), qty=1.0, is_buyer_maker=False)
    agg.mark_disconnected(T0 + timedelta(seconds=15))

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.coverage_seconds == pytest.approx(15.0)


def test_coverage_adds_up_across_a_reconnect_inside_one_minute() -> None:
    agg = OrderflowAggregator()
    agg.mark_connected(T0)
    agg.add_trade(SYMBOL, T0, qty=1.0, is_buyer_maker=False)
    agg.mark_disconnected(T0 + timedelta(seconds=10))
    agg.mark_connected(T0 + timedelta(seconds=40))

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.coverage_seconds == pytest.approx(30.0)  # 10 + 20


def test_each_symbol_and_minute_gets_its_own_bucket() -> None:
    agg = OrderflowAggregator()
    agg.add_trade("BTCUSDT", T0, qty=1.0, is_buyer_maker=False)
    agg.add_trade("ETHUSDT", T0, qty=2.0, is_buyer_maker=False)
    agg.add_trade("BTCUSDT", T0 + timedelta(minutes=1), qty=3.0, is_buyer_maker=False)

    rows = agg.take_closed(T0 + timedelta(minutes=2))
    assert [(row.symbol, row.ts, row.buy_vol) for row in rows] == [
        ("BTCUSDT", T0, 1.0),
        ("ETHUSDT", T0, 2.0),
        ("BTCUSDT", T0 + timedelta(minutes=1), 3.0),
    ]


def test_a_minute_without_book_samples_leaves_book_fields_unset() -> None:
    """Kitap örneği yoksa alan `None` kalır: sıfır yazmak "denge var" demek olurdu."""
    agg = OrderflowAggregator()
    agg.add_trade(SYMBOL, T0, qty=1.0, is_buyer_maker=False)

    row = agg.take_closed(T0 + timedelta(minutes=1))[0]
    assert row.top20_imbalance is None
    assert row.spread_bps is None
    assert row.top20_bid_qty is None
