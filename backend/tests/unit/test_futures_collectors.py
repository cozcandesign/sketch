"""Türev REST toplayıcıları: yazma, idempotanlık, kesme ve hata davranışı."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from marketpulse.collectors.binance_client import BinanceClient
from marketpulse.collectors.binance_futures import (
    FUNDING_RATE_PATH,
    GLOBAL_LONG_SHORT_PATH,
    OPEN_INTEREST_HIST_PATH,
    OPEN_INTEREST_PATH,
    PREMIUM_INDEX_PATH,
    TAKER_VOLUME_PATH,
    TOP_ACCOUNT_PATH,
    TOP_POSITION_PATH,
    FuturesClient,
)
from marketpulse.collectors.futures import (
    FundingCollector,
    LongShortCollector,
    OpenInterestCollector,
    TakerVolumeCollector,
)
from marketpulse.core.clock import FakeClock
from marketpulse.engine.ratelimit import RateLimiter
from marketpulse.storage import SqliteRepository, make_engine
from tests.fixtures.binance import (
    FUTURES_T0,
    funding_rate_rows,
    long_short_rows,
    open_interest_hist_rows,
    open_interest_live,
    premium_index,
    taker_volume_rows,
)

BASE = "https://fapi.test"
NOW = FUTURES_T0 + timedelta(hours=1)
SYMBOLS = ["BTCUSDT"]


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    repository = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repository.create_all()
    yield repository
    await repository.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def futures(clock: FakeClock) -> FuturesClient:
    limiter = RateLimiter(clock, name="binance_futures")
    return FuturesClient(BinanceClient(BASE, limiter, sleep=_no_sleep))


@respx.mock
async def test_funding_backfill_and_live_poll_write_rows(
    repo: SqliteRepository, clock: FakeClock, futures: FuturesClient
) -> None:
    respx.get(f"{BASE}{FUNDING_RATE_PATH}").mock(
        return_value=httpx.Response(200, json=funding_rate_rows(count=3))
    )
    respx.get(f"{BASE}{PREMIUM_INDEX_PATH}").mock(
        return_value=httpx.Response(200, json=premium_index())
    )
    collector = FundingCollector(futures, repo, clock, symbols=SYMBOLS)

    assert await collector.backfill() == 3
    assert await collector.poll_live() == 1

    history = await repo.get_funding_rates("BTCUSDT")
    live = await repo.get_funding_live("BTCUSDT")
    assert [row.funding_time for row in history] == [
        FUTURES_T0 + timedelta(hours=8 * i) for i in range(3)
    ]
    assert live[0].last_rate == pytest.approx(0.000125)


@respx.mock
async def test_writing_the_same_window_twice_does_not_duplicate_rows(
    repo: SqliteRepository, clock: FakeClock, futures: FuturesClient
) -> None:
    """Toplayıcılar örtüşen pencereler çeker; upsert idempotent olmalı."""
    respx.get(f"{BASE}{OPEN_INTEREST_HIST_PATH}").mock(
        return_value=httpx.Response(200, json=open_interest_hist_rows(count=4))
    )
    collector = OpenInterestCollector(futures, repo, clock, symbols=SYMBOLS)

    await collector.backfill()
    await collector.backfill()

    rows = await repo.get_open_interest("BTCUSDT")
    assert len(rows) == 4


@respx.mock
async def test_live_open_interest_does_not_overwrite_the_history_grid(
    repo: SqliteRepository, clock: FakeClock, futures: FuturesClient
) -> None:
    """Aynı `ts`'te canlı okuma geçmiş satırını güncelleyebilir; kaynak etiketi doğru kalmalı."""
    respx.get(f"{BASE}{OPEN_INTEREST_PATH}").mock(
        return_value=httpx.Response(200, json=open_interest_live())
    )
    collector = OpenInterestCollector(futures, repo, clock, symbols=SYMBOLS)

    await collector.poll_live()

    rows = await repo.get_open_interest("BTCUSDT")
    assert len(rows) == 1
    assert rows[0].source == "live"
    assert rows[0].ts == FUTURES_T0


@respx.mock
async def test_long_short_collector_stores_all_three_kinds(
    repo: SqliteRepository, futures: FuturesClient
) -> None:
    for path in (GLOBAL_LONG_SHORT_PATH, TOP_ACCOUNT_PATH, TOP_POSITION_PATH):
        respx.get(f"{BASE}{path}").mock(
            return_value=httpx.Response(200, json=long_short_rows(count=2))
        )
    collector = LongShortCollector(futures, repo, symbols=SYMBOLS)

    assert await collector.poll() == 6

    rows = await repo.get_long_short("BTCUSDT")
    assert {row.kind for row in rows} == {"global_account", "top_account", "top_position"}
    only_global = await repo.get_long_short("BTCUSDT", kind="global_account")
    assert len(only_global) == 2


@respx.mock
async def test_taker_volume_collector_writes_rows(
    repo: SqliteRepository, futures: FuturesClient
) -> None:
    respx.get(f"{BASE}{TAKER_VOLUME_PATH}").mock(
        return_value=httpx.Response(200, json=taker_volume_rows(count=3))
    )
    collector = TakerVolumeCollector(futures, repo, symbols=SYMBOLS)

    assert await collector.poll() == 3
    rows = await repo.get_taker_volume("BTCUSDT")
    assert rows[0].buy_vol > rows[0].sell_vol


@respx.mock
async def test_reads_are_cut_at_as_of(
    repo: SqliteRepository, clock: FakeClock, futures: FuturesClient
) -> None:
    """Point-in-time kuralı depo katmanında da geçerli: `ts <= as_of` (CLAUDE.md §9.3)."""
    respx.get(f"{BASE}{OPEN_INTEREST_HIST_PATH}").mock(
        return_value=httpx.Response(200, json=open_interest_hist_rows(count=4))
    )
    await OpenInterestCollector(futures, repo, clock, symbols=SYMBOLS).backfill()

    cut = FUTURES_T0 + timedelta(minutes=5)
    rows = await repo.get_open_interest("BTCUSDT", as_of=cut)
    assert [row.ts for row in rows] == [FUTURES_T0, cut]


@respx.mock
async def test_a_failing_endpoint_raises_to_the_caller_not_silently(
    repo: SqliteRepository, clock: FakeClock, futures: FuturesClient
) -> None:
    """Collector hatayı yutmaz; engine işi yakalar, sağlık kaydına yazar (CLAUDE.md §6)."""
    respx.get(f"{BASE}{PREMIUM_INDEX_PATH}").mock(return_value=httpx.Response(400, text="bad"))
    collector = FundingCollector(futures, repo, clock, symbols=SYMBOLS)

    with pytest.raises(Exception, match="400"):
        await collector.poll_live()
    assert await repo.get_funding_live("BTCUSDT") == []


@respx.mock
async def test_an_empty_history_is_not_an_error(
    repo: SqliteRepository, clock: FakeClock, futures: FuturesClient
) -> None:
    respx.get(f"{BASE}{FUNDING_RATE_PATH}").mock(return_value=httpx.Response(200, json=[]))
    assert await FundingCollector(futures, repo, clock, symbols=SYMBOLS).backfill() == 0


@respx.mock
async def test_backfill_asks_for_ninety_days_of_funding(
    repo: SqliteRepository, clock: FakeClock, futures: FuturesClient
) -> None:
    route = respx.get(f"{BASE}{FUNDING_RATE_PATH}").mock(return_value=httpx.Response(200, json=[]))
    await FundingCollector(futures, repo, clock, symbols=SYMBOLS).backfill()

    start_ms = int(route.calls.last.request.url.params["startTime"])
    requested = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
    assert NOW - requested == timedelta(days=90)
