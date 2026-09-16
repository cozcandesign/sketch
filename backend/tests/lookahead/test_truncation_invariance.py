"""Kesme değişmezliği: `as_of` ile alınan veri, DB `as_of`'ta kesilmiş gibi olmalı.

CLAUDE.md §9 madde 7(a) ve (b): kesme değişmezliği ve gelecek perturbasyonu.
"""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from marketpulse.core.types import Horizon, Interval
from marketpulse.features.feature_store import FeatureStore
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.models import FundingRate, OpenInterestPoint, OrderflowRow
from marketpulse.tracking import baselines
from tests.lookahead.conftest import SERIES_START, corrupt_after, random_walk

AS_OF_OFFSETS = [17, 41, 63, 99, 128]


@pytest.mark.parametrize("offset", AS_OF_OFFSETS)
async def test_candles_as_of_equals_truncated_database(repo: SqliteRepository, offset: int) -> None:
    candles = random_walk(200, Interval.M15)
    as_of = SERIES_START + offset * Interval.M15.length
    await repo.upsert_candles(candles)
    with_full_db = await repo.get_candles("BTCUSDT", Interval.M15, as_of=as_of)

    truncated_engine = make_engine("sqlite+aiosqlite:///:memory:")
    truncated = SqliteRepository(truncated_engine)
    await truncated.create_all()
    await truncated.upsert_candles([c for c in candles if c.close_time <= as_of])
    with_truncated_db = await truncated.get_candles("BTCUSDT", Interval.M15, as_of=None)
    await truncated.close()

    assert with_full_db == with_truncated_db
    assert all(c.close_time <= as_of for c in with_full_db)


async def test_open_candle_is_never_returned(repo: SqliteRepository) -> None:
    candles = random_walk(10, Interval.H1)
    await repo.upsert_candles(candles)
    # 3. mum 03:00'te açılır, 04:00'te kapanır; as_of=03:30 iken görülmemeli
    as_of = SERIES_START + timedelta(hours=3, minutes=30)
    visible = await repo.get_candles("BTCUSDT", Interval.H1, as_of=as_of)
    assert [c.open_time for c in visible] == [
        SERIES_START + i * Interval.H1.length for i in range(3)
    ]


@pytest.mark.parametrize("horizon", list(Horizon))
async def test_baselines_unchanged_by_future_data(repo: SqliteRepository, horizon: Horizon) -> None:
    """Gelecek perturbasyonu: as_of sonrası mumlar bozulsa da geçmiş tahmin değişmez."""
    intervals = {horizon.base_interval, horizon.context_interval}
    as_of = SERIES_START + 120 * Interval.M5.length
    series = {i: random_walk(400, i) for i in intervals}
    for candles in series.values():
        await repo.upsert_candles(candles)

    before_climatology = await baselines.climatology(repo, "BTCUSDT", horizon, as_of)
    before_momentum = await baselines.momentum(repo, "BTCUSDT", horizon, as_of)

    for interval, candles in series.items():
        await repo.upsert_candles(corrupt_after(candles, as_of))
        assert await repo.count_candles("BTCUSDT", interval) == len(candles)

    assert await baselines.climatology(repo, "BTCUSDT", horizon, as_of) == before_climatology
    assert await baselines.momentum(repo, "BTCUSDT", horizon, as_of) == before_momentum


@pytest.mark.parametrize("interval", list(Interval))
async def test_feature_snapshot_equals_the_truncated_database(
    repo: SqliteRepository, interval: Interval
) -> None:
    """Snapshot, DB `as_of`'ta kesilmiş gibi olmalı — her zaman diliminde (F2-2)."""
    candles = random_walk(300, interval)
    as_of = SERIES_START + 187 * interval.length + interval.length / 3
    await repo.upsert_candles(candles)
    full = await FeatureStore(repo).snapshot("BTCUSDT", as_of, intervals=[interval])

    truncated_engine = make_engine("sqlite+aiosqlite:///:memory:")
    truncated_repo = SqliteRepository(truncated_engine)
    await truncated_repo.create_all()
    await truncated_repo.upsert_candles([c for c in candles if c.close_time <= as_of])
    truncated = await FeatureStore(truncated_repo).snapshot("BTCUSDT", as_of, intervals=[interval])
    await truncated_repo.close()

    assert full.frame(interval).equals(truncated.frame(interval))
    assert full.price == truncated.price
    assert full.coverage == truncated.coverage


@pytest.mark.parametrize("interval", list(Interval))
async def test_feature_snapshot_ignores_corrupted_future_candles(
    repo: SqliteRepository, interval: Interval
) -> None:
    """Gelecek perturbasyonu: `as_of` sonrası mumlar bozulsa da snapshot değişmez."""
    candles = random_walk(300, interval)
    as_of = SERIES_START + 200 * interval.length
    await repo.upsert_candles(candles)
    store = FeatureStore(repo)
    before = await store.snapshot("BTCUSDT", as_of, intervals=[interval])

    await repo.upsert_candles(corrupt_after(candles, as_of))
    after = await store.snapshot("BTCUSDT", as_of, intervals=[interval])

    assert before.frame(interval).equals(after.frame(interval))
    assert before.price == after.price


def orderflow_series(count: int, *, start: datetime = SERIES_START) -> list[OrderflowRow]:
    """Dakikalık order flow serisi (deterministik)."""
    return [
        OrderflowRow(
            symbol="BTCUSDT",
            ts=start + timedelta(minutes=index),
            buy_vol=1.0 + (index % 7),
            sell_vol=0.5 + (index % 5),
            cvd_delta=0.5 + (index % 3),
            trade_count=10 + index,
            liq_long_usd=100.0 * (index % 4),
            liq_short_usd=50.0 * (index % 3),
            liq_count=index % 4,
            top20_imbalance=((index % 5) - 2) / 10.0,
            coverage_seconds=60.0,
        )
        for index in range(count)
    ]


async def test_order_flow_snapshot_equals_the_truncated_database(repo: SqliteRepository) -> None:
    """Türev veri setleri de `as_of`'ta kesilmiş DB ile birebir aynı olmalı (F3-4)."""
    rows = orderflow_series(600)
    as_of = SERIES_START + timedelta(minutes=407)
    await repo.upsert_orderflow(rows)
    full = await FeatureStore(repo).snapshot("BTCUSDT", as_of, intervals=[Interval.M1])

    truncated_repo = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await truncated_repo.create_all()
    await truncated_repo.upsert_orderflow([row for row in rows if row.ts <= as_of])
    truncated = await FeatureStore(truncated_repo).snapshot(
        "BTCUSDT", as_of, intervals=[Interval.M1]
    )
    await truncated_repo.close()

    assert full.dataset("orderflow_1m").equals(truncated.dataset("orderflow_1m"))
    assert full.coverage["orderflow_1m"] == truncated.coverage["orderflow_1m"]


async def test_order_flow_snapshot_ignores_rows_written_after_as_of(
    repo: SqliteRepository,
) -> None:
    """Gelecek perturbasyonu: `as_of` sonrası satırlar değişse de snapshot aynı kalır."""
    rows = orderflow_series(300)
    as_of = SERIES_START + timedelta(minutes=200)
    await repo.upsert_orderflow(rows)
    store = FeatureStore(repo)
    before = await store.snapshot("BTCUSDT", as_of, intervals=[Interval.M1])

    corrupted = [
        row.model_copy(update={"buy_vol": 9999.0, "cvd_delta": -9999.0})
        for row in rows
        if row.ts > as_of
    ]
    await repo.upsert_orderflow(corrupted)
    after = await store.snapshot("BTCUSDT", as_of, intervals=[Interval.M1])

    assert before.dataset("orderflow_1m").equals(after.dataset("orderflow_1m"))


async def test_funding_and_open_interest_are_cut_at_as_of(repo: SqliteRepository) -> None:
    await repo.upsert_funding_rates(
        [
            FundingRate(
                symbol="BTCUSDT",
                funding_time=SERIES_START + timedelta(hours=8 * index),
                rate=0.0001 * index,
            )
            for index in range(6)
        ]
    )
    await repo.upsert_open_interest(
        [
            OpenInterestPoint(
                symbol="BTCUSDT",
                ts=SERIES_START + timedelta(minutes=5 * index),
                oi=1000.0 + index,
                source="hist",
            )
            for index in range(20)
        ]
    )
    as_of = SERIES_START + timedelta(hours=17)
    snapshot = await FeatureStore(repo).snapshot("BTCUSDT", as_of, intervals=[Interval.M1])

    assert len(snapshot.dataset("funding")) == 3  # 0, 8, 16. saatler
    assert snapshot.dataset("open_interest").index.max() <= pd.Timestamp(as_of)
