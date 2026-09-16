"""Canlı tahmin akışı uçtan uca: mumlar → snapshot → modül → ensemble → rapor → defter.

Ağ yok: mumlar doğrudan DB'ye yazılır, gerçek kod yolu çalışır.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Horizon, Interval
from marketpulse.engine.predict import LivePredictor, run_baseline_predictions
from marketpulse.ensemble.combine import ENSEMBLE_VERSION
from marketpulse.ensemble.weights import load_default_weights
from marketpulse.features.feature_store import FeatureStore
from marketpulse.features.snapshot import FeatureSnapshot
from marketpulse.reporting.banned_words import find_banned
from marketpulse.signals.base import ModuleName, SignalResult
from marketpulse.signals.technical import TechnicalModule
from marketpulse.storage import Candle, Outbox, SqliteRepository, make_engine
from marketpulse.storage.models import FundingRate, OpenInterestPoint, OrderflowRow
from marketpulse.tracking.ledger import Ledger

START = datetime(2026, 2, 1, tzinfo=UTC)
AS_OF = START + timedelta(days=20)
SYMBOL = "BTCUSDT"
INTERVALS = (Interval.M1, Interval.M5, Interval.M15, Interval.H1, Interval.H4, Interval.D1)


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    repository = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repository.create_all()
    yield repository
    await repository.close()


def rising_candles(interval: Interval, count: int) -> list[Candle]:
    """Yükselen, hacmi artan seri: teknik modülün pozitif skor vermesi beklenir."""
    candles: list[Candle] = []
    for index in range(count):
        open_time = AS_OF - (count - index) * interval.length
        price = 100.0 * (1.0 + 0.0008 * index)
        candles.append(
            Candle(
                symbol=SYMBOL,
                interval=interval,
                open_time=open_time,
                open=price,
                high=price * 1.002,
                low=price * 0.998,
                close=price * 1.001,
                volume=10.0 + index * 0.05,
                quote_volume=1000.0,
                trades=20,
                taker_buy_base=6.0,
                close_time=open_time + interval.length,
            )
        )
    return candles


async def seed_market(repo: SqliteRepository, *, count: int = 320) -> None:
    for interval in INTERVALS:
        await repo.upsert_candles(rising_candles(interval, count))


def predictor_for(repo: SqliteRepository, clock: FakeClock) -> LivePredictor:
    ledger = Ledger(repo, clock, Outbox(repo, clock))
    return LivePredictor(repo, ledger, FeatureStore(repo))


async def test_a_live_prediction_is_written_with_signals_and_a_report(
    repo: SqliteRepository,
) -> None:
    await seed_market(repo)
    clock = FakeClock(AS_OF)
    written = await predictor_for(repo, clock).run(
        symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF
    )
    assert written == 1

    predictions = await repo.list_predictions(source="live")
    assert len(predictions) == 1
    prediction = await repo.get_prediction(predictions[0].id)
    assert prediction is not None
    assert prediction.source == "live"
    assert prediction.ensemble_version == ENSEMBLE_VERSION
    assert 0.10 <= prediction.p_up <= 0.90  # K19
    assert prediction.target_at == AS_OF + Horizon.H1H.length
    assert prediction.signals is not None
    modules = {row.module: row for row in prediction.signals}
    assert set(modules) == {"technical", "orderflow"}
    assert modules["technical"].rationale
    # Bu testte türev verisi yok: order flow "veri yok" der ve ensemble ağırlığını dağıtır.
    assert modules["orderflow"].coverage == 0.0
    assert prediction.report is not None
    assert prediction.report["missing"] == ["orderflow"]


async def test_the_report_is_complete_and_free_of_banned_words(repo: SqliteRepository) -> None:
    await seed_market(repo)
    clock = FakeClock(AS_OF)
    await predictor_for(repo, clock).run(symbols=[SYMBOL], horizon=Horizon.H4H, as_of=AS_OF)

    prediction = (await repo.list_predictions(source="live"))[0]
    report = prediction.report
    assert report is not None
    assert set(report) >= {
        "headline",
        "reasons",
        "counter_argument",
        "expected_range",
        "confidence",
        "data_coverage",
        "missing",
    }
    texts = [report["headline"], report["counter_argument"]]
    texts.extend(reason["text"] for reason in report["reasons"])
    for text in texts:
        assert find_banned(text) == [], text


async def test_an_upward_market_produces_a_probability_above_a_half(
    repo: SqliteRepository,
) -> None:
    await seed_market(repo)
    clock = FakeClock(AS_OF)
    await predictor_for(repo, clock).run(symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF)
    prediction = (await repo.list_predictions(source="live"))[0]
    assert prediction.p_up > 0.5
    assert prediction.combined_score is not None
    assert prediction.combined_score > 0


async def test_a_broken_module_becomes_no_data_instead_of_killing_the_prediction(
    repo: SqliteRepository,
) -> None:
    """CLAUDE.md §6: tek modülün hatası sistemi durdurmaz."""

    class BrokenModule:
        name: ModuleName = "orderflow"

        def compute(self, snapshot: FeatureSnapshot, horizon: Horizon) -> SignalResult:
            msg = "bilerek bozuk modül"
            raise RuntimeError(msg)

    await seed_market(repo)
    clock = FakeClock(AS_OF)
    ledger = Ledger(repo, clock, Outbox(repo, clock))
    predictor = LivePredictor(
        repo, ledger, FeatureStore(repo), modules=[TechnicalModule(), BrokenModule()]
    )
    written = await predictor.run(symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF)

    assert written == 1
    prediction = await repo.get_prediction((await repo.list_predictions(source="live"))[0].id)
    assert prediction is not None
    assert prediction.report is not None
    assert prediction.report["missing"] == ["orderflow"]
    assert prediction.signals is not None
    assert {row.module for row in prediction.signals} == {"technical", "orderflow"}


async def test_without_candles_no_live_prediction_is_written(repo: SqliteRepository) -> None:
    clock = FakeClock(AS_OF)
    written = await predictor_for(repo, clock).run(
        symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF
    )
    assert written == 0
    assert await repo.list_predictions(source="live") == []


async def test_stored_weights_take_precedence_over_the_yaml_defaults(
    repo: SqliteRepository,
) -> None:
    """K3: kullanıcının onayladığı ağırlıklar YAML tarafından ezilmez."""
    await seed_market(repo)
    await repo.seed_weights({Horizon.H1H: {"technical": 0.5, "orderflow": 0.5}}, valid_from=START)
    clock = FakeClock(AS_OF)
    await predictor_for(repo, clock).run(symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF)

    prediction = (await repo.list_predictions(source="live"))[0]
    assert prediction.weights is not None
    default_weight = load_default_weights()[Horizon.H1H]["technical"]
    assert prediction.weights["technical"] != pytest.approx(default_weight)


async def test_live_and_baseline_predictions_live_side_by_side(repo: SqliteRepository) -> None:
    await seed_market(repo)
    clock = FakeClock(AS_OF)
    ledger = Ledger(repo, clock, Outbox(repo, clock))
    predictor = LivePredictor(repo, ledger, FeatureStore(repo))

    await predictor.run(symbols=[SYMBOL], horizon=Horizon.H24H, as_of=AS_OF)
    await run_baseline_predictions(
        repo, ledger, symbols=[SYMBOL], horizon=Horizon.H24H, as_of=AS_OF
    )

    assert len(await repo.list_predictions(source="live")) == 1
    assert len(await repo.list_predictions(source="baseline")) == 2


async def test_the_prediction_event_reaches_the_outbox(repo: SqliteRepository) -> None:
    await seed_market(repo)
    clock = FakeClock(AS_OF)
    await predictor_for(repo, clock).run(symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF)

    events = await repo.outbox_read_after(0)
    topics = [event.topic for event in events]
    assert "prediction.created" in topics


async def orderflow_history(repo: SqliteRepository, *, minutes: int = 240) -> None:
    """Dakikalık order flow geçmişi: agresif alım baskısı ve dolu order book."""
    rows = [
        OrderflowRow(
            symbol=SYMBOL,
            ts=AS_OF - timedelta(minutes=minutes - index),
            buy_vol=12.0,
            sell_vol=8.0,
            cvd_delta=4.0,
            trade_count=40,
            liq_long_usd=0.0,
            liq_short_usd=0.0,
            liq_count=0,
            top20_imbalance=0.25,
            depth1pct_imbalance=0.2,
            coverage_seconds=60.0,
        )
        for index in range(minutes)
    ]
    await repo.upsert_orderflow(rows)
    await repo.upsert_open_interest(
        [
            OpenInterestPoint(
                symbol=SYMBOL,
                ts=AS_OF - timedelta(minutes=5 * (60 - index)),
                oi=1000.0 + index * 4.0,
                source="hist",
            )
            for index in range(60)
        ]
    )
    await repo.upsert_funding_rates(
        [
            FundingRate(
                symbol=SYMBOL,
                funding_time=AS_OF - timedelta(hours=8 * (20 - index)),
                rate=0.0001,
            )
            for index in range(20)
        ]
    )


async def test_order_flow_joins_the_prediction_when_its_data_exists(
    repo: SqliteRepository,
) -> None:
    await seed_market(repo)
    await orderflow_history(repo)
    clock = FakeClock(AS_OF)
    await predictor_for(repo, clock).run(symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF)

    prediction = await repo.get_prediction((await repo.list_predictions(source="live"))[0].id)
    assert prediction is not None
    assert prediction.signals is not None
    orderflow = next(row for row in prediction.signals if row.module == "orderflow")
    assert orderflow.coverage > 0
    assert orderflow.rationale
    assert prediction.report is not None
    assert prediction.report["missing"] == []
    assert prediction.weights is not None
    assert set(prediction.weights) == {"technical", "orderflow"}


async def test_an_order_flow_outage_lowers_confidence_but_still_predicts(
    repo: SqliteRepository,
) -> None:
    """WS kesintisi: kapsama düşer, tahmin yine üretilir, güven azalır (Faz 3 bitti ölçütü)."""
    await seed_market(repo)
    await orderflow_history(repo)
    clock = FakeClock(AS_OF)
    predictor = predictor_for(repo, clock)
    await predictor.run(symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF)
    healthy = (await repo.list_predictions(source="live"))[0]

    # Aynı dakikalar, ama bağlantı dakikanın yalnızca 6 saniyesinde açıkmış.
    await repo.upsert_orderflow(
        [
            OrderflowRow(symbol=SYMBOL, ts=AS_OF - timedelta(minutes=index), coverage_seconds=6.0)
            for index in range(240)
        ]
    )
    await predictor.run(symbols=[SYMBOL], horizon=Horizon.H1H, as_of=AS_OF)
    degraded = (await repo.list_predictions(source="live"))[0]

    assert degraded.id != healthy.id
    assert degraded.confidence < healthy.confidence
    assert degraded.p_up != 0.5 or degraded.combined_score is not None  # tahmin yine üretildi
