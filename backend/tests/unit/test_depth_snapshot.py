"""±%1 derinlik özeti: bant sınırı, dengesizlik işareti ve sütun sahipliği."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import respx

from marketpulse.collectors.binance_client import BinanceClient
from marketpulse.collectors.binance_futures import DEPTH_PATH, DepthSnapshot, FuturesClient
from marketpulse.collectors.depth_snapshot import DepthSnapshotCollector, summarize
from marketpulse.core.clock import FakeClock
from marketpulse.engine.ratelimit import RateLimiter
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.models import OrderflowRow

BASE = "https://fapi.test"
T0 = datetime(2026, 3, 1, 12, 0, 30, tzinfo=UTC)
MINUTE = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"


async def _no_sleep(_seconds: float) -> None:
    return None


@pytest.fixture
async def repo() -> AsyncIterator[SqliteRepository]:
    repository = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repository.create_all()
    yield repository
    await repository.close()


@pytest.fixture
def futures() -> FuturesClient:
    limiter = RateLimiter(FakeClock(T0), name="binance_futures")
    return FuturesClient(BinanceClient(BASE, limiter, sleep=_no_sleep))


def depth_payload(bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> dict:
    return {
        "lastUpdateId": 1027024,
        "E": 1589436922972,
        "T": 1589436922959,
        "bids": [[f"{p:.2f}", f"{q:.4f}"] for p, q in bids],
        "asks": [[f"{p:.2f}", f"{q:.4f}"] for p, q in asks],
    }


def test_only_levels_inside_the_one_percent_band_are_counted() -> None:
    snapshot = DepthSnapshot(
        symbol=SYMBOL,
        bids=[(100.0, 1.0), (99.5, 2.0), (90.0, 100.0)],  # 90 bandın dışında
        asks=[(100.5, 1.0), (101.0, 1.0), (110.0, 100.0)],  # 110 bandın dışında
    )
    summary = summarize(snapshot)

    assert summary is not None
    assert summary.bid_usd == pytest.approx(100.0 * 1.0 + 99.5 * 2.0)
    assert summary.ask_usd == pytest.approx(100.5 * 1.0 + 101.0 * 1.0)


def test_a_heavier_bid_side_gives_a_positive_imbalance() -> None:
    snapshot = DepthSnapshot(symbol=SYMBOL, bids=[(100.0, 9.0)], asks=[(100.5, 1.0)])
    summary = summarize(snapshot)

    assert summary is not None
    assert summary.imbalance is not None
    assert summary.imbalance > 0.7


def test_spread_is_reported_in_basis_points() -> None:
    snapshot = DepthSnapshot(symbol=SYMBOL, bids=[(99.9, 1.0)], asks=[(100.1, 1.0)])
    summary = summarize(snapshot)

    assert summary is not None
    assert summary.spread_bps == pytest.approx(0.2 / 100.0 * 10_000)


def test_an_empty_book_yields_no_summary() -> None:
    assert summarize(DepthSnapshot(symbol=SYMBOL, bids=[], asks=[])) is None


@respx.mock
async def test_the_collector_writes_only_the_depth_columns(
    repo: SqliteRepository, futures: FuturesClient
) -> None:
    """WS'in yazdığı hacim ve spread sütunlarına dokunulmaz."""
    await repo.upsert_orderflow(
        [OrderflowRow(symbol=SYMBOL, ts=MINUTE, buy_vol=5.0, spread_bps=1.5, trade_count=3)]
    )
    respx.get(f"{BASE}{DEPTH_PATH}").mock(
        return_value=httpx.Response(
            200, json=depth_payload([(100.0, 2.0)], [(100.5, 1.0)])
        )
    )
    collector = DepthSnapshotCollector(futures, repo, FakeClock(T0), symbols=[SYMBOL])

    assert await collector.poll() == 1

    row = (await repo.get_orderflow(SYMBOL))[0]
    assert row.ts == MINUTE  # dakikaya hizalanır
    assert row.depth1pct_bid_usd == pytest.approx(200.0)
    assert row.depth1pct_ask_usd == pytest.approx(100.5)
    assert row.buy_vol == pytest.approx(5.0)
    assert row.spread_bps == pytest.approx(1.5)  # WS'in ölçümü korunur
    assert row.trade_count == 3


@respx.mock
async def test_an_empty_book_writes_nothing(
    repo: SqliteRepository, futures: FuturesClient
) -> None:
    respx.get(f"{BASE}{DEPTH_PATH}").mock(
        return_value=httpx.Response(200, json=depth_payload([], []))
    )
    collector = DepthSnapshotCollector(futures, repo, FakeClock(T0), symbols=[SYMBOL])

    assert await collector.poll() == 0
    assert await repo.get_orderflow(SYMBOL) == []
