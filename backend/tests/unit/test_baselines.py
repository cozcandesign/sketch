from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.types import Horizon, Interval
from marketpulse.storage import Candle, SqliteRepository, make_engine
from marketpulse.tracking import baselines

NOW = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    repository = SqliteRepository(engine)
    await repository.create_all()
    yield repository
    await repository.close()


def candles(interval: Interval, closes: list[float], *, end: datetime = NOW) -> list[Candle]:
    """`end` anında biten, artan sırada mum serisi."""
    result = []
    for index, close in enumerate(reversed(closes)):
        close_time = end - index * interval.length
        open_time = close_time - interval.length
        previous = close * 0.999
        result.append(
            Candle(
                symbol="BTCUSDT",
                interval=interval,
                open_time=open_time,
                open=previous,
                high=max(previous, close),
                low=min(previous, close),
                close=close,
                volume=1.0,
                close_time=close_time,
            )
        )
    return list(reversed(result))


async def test_climatology_counts_up_windows(repo: SqliteRepository) -> None:
    # 1s ufku, ana zaman dilimi 15dk → adım 4. Sürekli artan seri: tüm pencereler yukarı.
    await repo.upsert_candles(candles(Interval.M15, [100.0 + i for i in range(100)]))
    result = await baselines.climatology(repo, "BTCUSDT", Horizon.H1H, NOW)
    assert result.version == "baseline-climatology-1"
    assert result.p_up == 1.0
    assert result.samples == 96
    assert "yukarı kapandı" in result.note_tr


async def test_climatology_half_up_half_down(repo: SqliteRepository) -> None:
    # Testere dişi: her 4 adımda bir yukarı, bir aşağı
    closes = []
    for i in range(100):
        closes.append(100.0 + (5.0 if (i // 4) % 2 == 0 else 0.0))
    await repo.upsert_candles(candles(Interval.M15, closes))
    result = await baselines.climatology(repo, "BTCUSDT", Horizon.H1H, NOW)
    assert 0.2 < result.p_up < 0.8


async def test_climatology_falls_back_to_half_without_history(repo: SqliteRepository) -> None:
    result = await baselines.climatology(repo, "BTCUSDT", Horizon.H4H, NOW)
    assert result.p_up == 0.5
    assert result.samples == 0
    assert "yeterli geçmiş yok" in result.note_tr


async def test_climatology_falls_back_when_samples_too_few(repo: SqliteRepository) -> None:
    await repo.upsert_candles(candles(Interval.M15, [100.0 + i for i in range(10)]))
    result = await baselines.climatology(repo, "BTCUSDT", Horizon.H1H, NOW)
    assert result.p_up == 0.5
    assert "örnek az" in result.note_tr


async def test_momentum_follows_last_context_candle(repo: SqliteRepository) -> None:
    # 1s ufku → bağlam 1s mumu. Son mum yeşil olacak şekilde artan seri.
    await repo.upsert_candles(candles(Interval.H1, [100.0, 101.0, 102.0]))
    result = await baselines.momentum(repo, "BTCUSDT", Horizon.H1H, NOW)
    assert result.p_up == 0.6
    assert "yeşil" in result.note_tr


async def test_momentum_red_candle(repo: SqliteRepository) -> None:
    red = candles(Interval.H1, [100.0])
    red = [red[0].model_copy(update={"open": 110.0, "close": 100.0})]
    await repo.upsert_candles(red)
    result = await baselines.momentum(repo, "BTCUSDT", Horizon.H1H, NOW)
    assert result.p_up == 0.4
    assert "kırmızı" in result.note_tr


async def test_momentum_without_candles(repo: SqliteRepository) -> None:
    result = await baselines.momentum(repo, "BTCUSDT", Horizon.H30M, NOW)
    assert result.p_up == 0.5
    assert result.samples == 0


async def test_baselines_only_see_closed_candles(repo: SqliteRepository) -> None:
    """as_of'tan sonra kapanan mum sonucu etkilememeli (look-ahead koruması)."""
    await repo.upsert_candles(candles(Interval.H1, [100.0, 101.0], end=NOW))
    future = candles(Interval.H1, [50.0], end=NOW + timedelta(hours=1))
    future = [future[0].model_copy(update={"open": 200.0, "close": 50.0})]
    await repo.upsert_candles(future)
    result = await baselines.momentum(repo, "BTCUSDT", Horizon.H1H, NOW)
    assert result.p_up == 0.6  # gelecekteki kırmızı mum görülmedi
