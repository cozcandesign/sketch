"""Kesme değişmezliği: `as_of` ile alınan veri, DB `as_of`'ta kesilmiş gibi olmalı.

CLAUDE.md §9 madde 7(a) ve (b): kesme değişmezliği ve gelecek perturbasyonu.
"""

from datetime import timedelta

import pytest

from marketpulse.core.types import Horizon, Interval
from marketpulse.storage import SqliteRepository, make_engine
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
