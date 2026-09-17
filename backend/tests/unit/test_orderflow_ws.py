"""Order flow WS toplayıcısı: mesaj ayrıştırma, yazma ve kopma davranışı (ağ yok)."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.collectors.orderflow_ws import (
    OrderflowWsCollector,
    parse_liquidation,
    streams_for,
)
from marketpulse.collectors.ws_stream import ConnectFactory
from marketpulse.core.clock import FakeClock
from marketpulse.engine.health import HealthRegistry
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.models import OrderflowRow
from tests.fixtures.binance import ws_agg_trade, ws_depth20, ws_force_order

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"


def fake_connect(messages: Iterable[dict[str, object]]) -> ConnectFactory:
    @contextlib.asynccontextmanager
    async def connect(_url: str) -> AsyncIterator[AsyncIterator[str]]:
        async def stream() -> AsyncIterator[str]:
            for message in messages:
                yield json.dumps(message)

        yield stream()

    return connect


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    repository = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repository.create_all()
    yield repository
    await repository.close()


def build(
    repo: SqliteRepository,
    clock: FakeClock,
    messages: Iterable[dict[str, object]],
    health: HealthRegistry | None = None,
) -> OrderflowWsCollector:
    return OrderflowWsCollector(
        "wss://test/stream",
        repo,
        clock,
        health or HealthRegistry(clock),
        symbols=[SYMBOL],
        connect=fake_connect(messages),
    )


def test_every_symbol_subscribes_to_three_streams() -> None:
    assert streams_for(["BTCUSDT", "ETHUSDT"]) == [
        "btcusdt@aggTrade",
        "btcusdt@forceOrder",
        "btcusdt@depth20@100ms",
        "ethusdt@aggTrade",
        "ethusdt@forceOrder",
        "ethusdt@depth20@100ms",
    ]


def test_a_forced_sell_is_a_long_liquidation() -> None:
    """Binance emir yönü verir: SELL → uzun pozisyon kapatıldı."""
    payload = ws_force_order(SYMBOL, side="SELL", qty=0.5, price=60000.0, ts=T0)["data"]
    liquidation = parse_liquidation(payload)

    assert liquidation is not None
    assert liquidation.side == "long"
    assert liquidation.usd == pytest.approx(30000.0)


def test_a_forced_buy_is_a_short_liquidation() -> None:
    payload = ws_force_order(SYMBOL, side="BUY", qty=0.2, price=60000.0, ts=T0)["data"]
    liquidation = parse_liquidation(payload)

    assert liquidation is not None
    assert liquidation.side == "short"


def test_an_unfilled_force_order_is_ignored() -> None:
    payload = ws_force_order(SYMBOL, side="SELL", qty=0.0, price=60000.0, ts=T0)["data"]
    assert parse_liquidation(payload) is None


async def test_a_closed_minute_is_written_with_trades_book_and_liquidations(
    repo: SqliteRepository,
) -> None:
    clock = FakeClock(T0)
    messages = [
        ws_agg_trade(SYMBOL, qty=1.5, price=60000.0, is_buyer_maker=False, ts=T0),
        ws_agg_trade(SYMBOL, qty=0.5, price=60000.0, is_buyer_maker=True, ts=T0),
        ws_depth20(SYMBOL, bids=[(59990.0, 4.0)], asks=[(60010.0, 2.0)], ts=T0),
        ws_force_order(SYMBOL, side="SELL", qty=0.25, price=60000.0, ts=T0),
    ]
    collector = build(repo, clock, messages)

    await collector.run(asyncio.Event())
    clock.set(T0 + timedelta(minutes=1))
    await collector.flush()

    rows = await repo.get_orderflow(SYMBOL)
    assert len(rows) == 1
    row = rows[0]
    assert row.buy_vol == pytest.approx(1.5)
    assert row.sell_vol == pytest.approx(0.5)
    assert row.cvd_delta == pytest.approx(1.0)
    assert row.trade_count == 2
    assert row.liq_long_usd == pytest.approx(15000.0)
    assert row.top20_imbalance == pytest.approx((4.0 - 2.0) / 6.0)
    assert row.spread_bps is not None
    assert row.spread_bps > 0

    liquidations = await repo.get_liquidations(SYMBOL)
    assert [liq.side for liq in liquidations] == ["long"]


async def test_liquidations_are_stored_raw_as_they_arrive(repo: SqliteRepository) -> None:
    clock = FakeClock(T0)
    messages = [
        ws_force_order(SYMBOL, side="SELL", qty=0.1, price=60000.0, ts=T0),
        ws_force_order(SYMBOL, side="BUY", qty=0.2, price=60100.0, ts=T0 + timedelta(seconds=5)),
    ]
    await build(repo, clock, messages).run(asyncio.Event())

    rows = await repo.get_liquidations(SYMBOL)
    assert [(row.side, round(row.usd)) for row in rows] == [("long", 6000), ("short", 12020)]


async def test_a_broken_message_does_not_stop_the_stream(repo: SqliteRepository) -> None:
    clock = FakeClock(T0)
    health = HealthRegistry(clock)
    collector = build(repo, clock, [], health)
    # Hata yolunu doğrudan çağırıyoruz: bozuk mesaj akışı durdurmamalı.
    await collector.handle_message("bu json değil")
    await collector.handle_message(json.dumps({"stream": "x", "data": {"e": "aggTrade"}}))

    assert collector.aggregator.open_minutes() == 0


async def test_an_unparsable_trade_is_recorded_not_swallowed(repo: SqliteRepository) -> None:
    """Alan adı değişirse akış sessizce sıfır hacim yazmamalı: hata sağlık kaydına düşer (F3-10)."""
    clock = FakeClock(T0)
    health = HealthRegistry(clock)
    collector = build(repo, clock, [], health)

    # "q" (miktar) alanı eksik: Binance şeması değişmiş gibi.
    await collector.handle_message(
        json.dumps({"stream": "btcusdt@aggTrade", "data": {"e": "aggTrade", "s": SYMBOL, "T": 1}})
    )

    entry = next(row for row in health.snapshot() if row.collector == "ws_orderflow")
    assert entry.consecutive_failures == 1
    assert entry.last_error is not None
    assert entry.last_success_at is None  # hata "başarı" diye kaydedilmedi


async def test_disconnecting_stops_the_coverage_clock_and_flushes(
    repo: SqliteRepository,
) -> None:
    """Akış bitince açık dakikalar yazılır ve kapsama süresi kopma anında durur."""
    clock = FakeClock(T0)
    trade = ws_agg_trade(SYMBOL, qty=1.0, price=1.0, is_buyer_maker=False, ts=T0)
    collector = build(repo, clock, [trade])

    await collector.run(asyncio.Event())
    clock.set(T0 + timedelta(minutes=2))
    await collector.flush()

    row = (await repo.get_orderflow(SYMBOL))[0]
    assert row.coverage_seconds == pytest.approx(0.0, abs=0.001)  # sahte saat ilerlemedi
    assert row.trade_count == 1


async def test_writes_do_not_erase_columns_written_by_another_source(
    repo: SqliteRepository,
) -> None:
    """REST derinlik anlık görüntüsü ve WS aynı dakikaya yazar; biri diğerini silmemeli."""
    await repo.upsert_orderflow(
        [OrderflowRow(symbol=SYMBOL, ts=T0, depth1pct_bid_usd=1000.0, depth1pct_imbalance=0.2)]
    )
    await repo.upsert_orderflow([OrderflowRow(symbol=SYMBOL, ts=T0, buy_vol=3.0, trade_count=7)])

    row = (await repo.get_orderflow(SYMBOL))[0]
    assert row.depth1pct_bid_usd == pytest.approx(1000.0)
    assert row.depth1pct_imbalance == pytest.approx(0.2)
    assert row.buy_vol == pytest.approx(3.0)
    assert row.trade_count == 7


class TestSilentTradeStreamIsVisible:
    """Derinlik akışı gelirken işlem akışı ölüyse şerit bunu göstermeli (K22, F3-13)."""

    def _ticking_connect(
        self, clock: FakeClock, messages: list[dict[str, object]], *, step: timedelta
    ) -> ConnectFactory:
        """Her mesajda saati ilerleten sahte akış: sessizlik süresi gerçekten geçsin."""

        @contextlib.asynccontextmanager
        async def connect(_url: str) -> AsyncIterator[AsyncIterator[str]]:
            async def stream() -> AsyncIterator[str]:
                for message in messages:
                    clock.set(clock.now() + step)
                    yield json.dumps(message)

            yield stream()

        return connect

    def _depth_messages(self, count: int) -> list[dict[str, object]]:
        return [
            ws_depth20(SYMBOL, bids=[(1.0, 2.0)], asks=[(3.0, 4.0)], ts=T0) for _ in range(count)
        ]

    async def _run_depth_only(
        self, repo: SqliteRepository, clock: FakeClock, health: HealthRegistry, *, minutes: int
    ) -> None:
        collector = OrderflowWsCollector(
            "wss://test/stream",
            repo,
            clock,
            health,
            symbols=[SYMBOL],
            connect=self._ticking_connect(
                clock, self._depth_messages(minutes), step=timedelta(minutes=1)
            ),
        )
        await collector.run(asyncio.Event())

    async def test_depth_alone_does_not_keep_the_collector_green(
        self, repo: SqliteRepository
    ) -> None:
        clock = FakeClock(T0)
        health = HealthRegistry(clock)
        health.register("ws_orderflow")

        await self._run_depth_only(repo, clock, health, minutes=7)

        assert health.status_of("ws_orderflow") == "degraded"
        entry = next(row for row in health.snapshot() if row.collector == "ws_orderflow")
        assert entry.last_error is not None
        assert "aggTrade" in entry.last_error

    async def test_it_does_not_cry_wolf_in_the_first_minutes(self, repo: SqliteRepository) -> None:
        """Yeni bağlanmış bir akış için sessizlik normaldir; eşik dolmadan alarm verilmez."""
        clock = FakeClock(T0)
        health = HealthRegistry(clock)
        health.register("ws_orderflow")

        await self._run_depth_only(repo, clock, health, minutes=3)

        assert health.status_of("ws_orderflow") == "ok"

    async def test_a_trade_clears_the_warning(self, repo: SqliteRepository) -> None:
        clock = FakeClock(T0)
        health = HealthRegistry(clock)
        health.register("ws_orderflow")
        messages: list[dict[str, object]] = self._depth_messages(7)
        messages.append(ws_agg_trade(SYMBOL, qty=1.0, price=1.0, is_buyer_maker=False, ts=T0))
        collector = OrderflowWsCollector(
            "wss://test/stream",
            repo,
            clock,
            health,
            symbols=[SYMBOL],
            connect=self._ticking_connect(clock, messages, step=timedelta(minutes=1)),
        )

        await collector.run(asyncio.Event())

        assert health.status_of("ws_orderflow") == "ok"
