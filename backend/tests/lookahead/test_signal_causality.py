"""Sinyal ve tahmin yolunun nedenselliği (CLAUDE.md §9 madde 7).

(b) gelecek perturbasyonu: `as_of` sonrası mumlar bozulsa da modül çıktısı ve tahmin değişmez.
(d) backtest eşdeğerliği iskeleti: aynı `as_of` için iki bağımsız çağrı birebir aynı sonucu verir.
    Backtest motoru Faz 7'de gelecek; bu test şimdiden "aynı as_of → aynı çıktı" sözleşmesini
    korur, motor eklendiğinde aynı yere motorun çağrısı konur.
"""

from datetime import timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.core.types import Horizon, Interval
from marketpulse.engine.predict import LivePredictor
from marketpulse.features.feature_store import FeatureStore
from marketpulse.signals.technical import TechnicalModule
from marketpulse.storage import Candle, Outbox, SqliteRepository
from marketpulse.tracking.ledger import Ledger
from tests.lookahead.conftest import SERIES_START, corrupt_after, random_walk

SYMBOL = "BTCUSDT"
INTERVALS = (Interval.M1, Interval.M5, Interval.M15, Interval.H1, Interval.H4, Interval.D1)
AS_OF = SERIES_START + timedelta(days=30)


async def seed(repo: SqliteRepository) -> dict[Interval, list[Candle]]:
    series: dict[Interval, list[Candle]] = {}
    for interval in INTERVALS:
        count = min(600, int(timedelta(days=60) / interval.length) + 300)
        candles = random_walk(count, interval, start=AS_OF - count * interval.length)
        series[interval] = candles
        await repo.upsert_candles(candles)
    return series


@pytest.mark.parametrize("horizon", list(Horizon))
async def test_technical_module_ignores_future_candles(
    repo: SqliteRepository, horizon: Horizon
) -> None:
    series = await seed(repo)
    store = FeatureStore(repo)
    module = TechnicalModule()

    before = module.compute(await store.snapshot(SYMBOL, AS_OF), horizon)
    for candles in series.values():
        await repo.upsert_candles(corrupt_after(candles, AS_OF))
    after = module.compute(await store.snapshot(SYMBOL, AS_OF), horizon)

    assert before == after


@pytest.mark.parametrize("horizon", list(Horizon))
async def test_the_written_prediction_ignores_future_candles(
    repo: SqliteRepository, horizon: Horizon
) -> None:
    """Tahmin yazımı da nedensel olmalı: gelecek bozulsa da aynı olasılık çıkar."""
    series = await seed(repo)
    clock = FakeClock(AS_OF)
    predictor = LivePredictor(repo, Ledger(repo, clock, Outbox(repo, clock)), FeatureStore(repo))

    await predictor.run(symbols=[SYMBOL], horizon=horizon, as_of=AS_OF)
    for candles in series.values():
        await repo.upsert_candles(corrupt_after(candles, AS_OF))
    await predictor.run(symbols=[SYMBOL], horizon=horizon, as_of=AS_OF)

    predictions = await repo.list_predictions(source="live", horizon=horizon)
    assert len(predictions) == 2
    first, second = predictions
    assert first.p_up == second.p_up
    assert first.combined_score == second.combined_score
    assert first.confidence == second.confidence
    assert first.report == second.report


@pytest.mark.parametrize("horizon", list(Horizon))
async def test_the_same_as_of_produces_the_same_signal_twice(
    repo: SqliteRepository, horizon: Horizon
) -> None:
    """Backtest eşdeğerliği iskeleti: aynı `as_of`, aynı `SignalResult` (Faz 7'de motorla kıyas)."""
    await seed(repo)
    store = FeatureStore(repo)
    module = TechnicalModule()

    live = module.compute(await store.snapshot(SYMBOL, AS_OF), horizon)
    replayed = module.compute(await store.snapshot(SYMBOL, AS_OF), horizon)

    assert live == replayed


async def test_a_later_as_of_sees_more_bars_than_an_earlier_one(repo: SqliteRepository) -> None:
    """Nedensellik tek yönlüdür: sonraki an daha çok veri görür, öncekinin verisi değişmez."""
    await seed(repo)
    store = FeatureStore(repo)
    earlier = await store.snapshot(SYMBOL, AS_OF - timedelta(hours=6))
    later = await store.snapshot(SYMBOL, AS_OF)

    assert later.bars(Interval.M15) > earlier.bars(Interval.M15)
    earlier_frame = earlier.frame(Interval.M15)
    assert later.frame(Interval.M15).head(len(earlier_frame)).equals(earlier_frame)
