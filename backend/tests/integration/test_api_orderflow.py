"""`/market/{symbol}/orderflow`: panel verisi, kümülatif CVD ve kapsama oranı."""

import asyncio
from collections.abc import Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.app import create_app
from marketpulse.config import Settings
from marketpulse.core.clock import FakeClock
from marketpulse.storage import SqliteRepository, make_engine
from marketpulse.storage.models import (
    FundingLive,
    FundingRate,
    Liquidation,
    LongShortPoint,
    OpenInterestPoint,
    OrderflowRow,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
SYMBOL = "BTCUSDT"


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _seed(settings: Settings) -> None:
    repo = SqliteRepository(make_engine(settings.db_url), db_url=settings.db_url)
    await repo.upsert_orderflow(
        [
            OrderflowRow(
                symbol=SYMBOL,
                ts=NOW - timedelta(minutes=index),
                buy_vol=10.0,
                sell_vol=8.0,
                cvd_delta=2.0,
                trade_count=25,
                liq_long_usd=0.0,
                liq_short_usd=1000.0 if index == 1 else 0.0,
                liq_count=1 if index == 1 else 0,
                top20_imbalance=0.1,
                depth1pct_imbalance=0.05,
                spread_bps=1.2,
                coverage_seconds=60.0,
            )
            for index in range(1, 61)
        ]
    )
    await repo.insert_liquidations(
        [
            Liquidation(
                symbol=SYMBOL,
                ts=NOW - timedelta(minutes=1),
                side="short",
                qty=0.02,
                price=60000.0,
                usd=1200.0,
            )
        ]
    )
    await repo.upsert_funding_rates(
        [
            FundingRate(
                symbol=SYMBOL,
                funding_time=NOW - timedelta(hours=8 * index),
                rate=0.0001 + 0.00001 * (index % 3),
            )
            for index in range(1, 30)
        ]
    )
    await repo.upsert_funding_live(
        [
            FundingLive(
                symbol=SYMBOL,
                ts=NOW - timedelta(minutes=1),
                last_rate=0.0004,
                next_funding_time=NOW + timedelta(hours=3),
                mark_price=60125.0,
            )
        ]
    )
    await repo.upsert_open_interest(
        [
            OpenInterestPoint(
                symbol=SYMBOL,
                ts=NOW - timedelta(hours=24) + timedelta(minutes=5 * index),
                oi=1000.0 + index,
                source="hist",
            )
            for index in range(0, 288)
        ]
    )
    await repo.upsert_long_short(
        [
            LongShortPoint(
                symbol=SYMBOL,
                ts=NOW - timedelta(minutes=5),
                kind=kind,
                long_ratio=0.6,
                short_ratio=0.4,
                ratio=1.5,
            )
            for kind in ("global_account", "top_account", "top_position")
        ]
    )
    await repo.close()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'orderflow.db'}",
        symbols=[SYMBOL],
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, clock=FakeClock(NOW), live_prices=False)
    with TestClient(app) as test_client:
        yield test_client


def test_orderflow_endpoint_returns_minutes_with_cumulative_cvd(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    body = client.get(f"/api/v1/market/{SYMBOL}/orderflow", params={"minutes": 60}).json()

    assert body["symbol"] == SYMBOL
    assert len(body["minutes"]) == 60
    first, last = body["minutes"][0], body["minutes"][-1]
    assert first["cvd_cumulative"] == pytest.approx(2.0)
    assert last["cvd_cumulative"] == pytest.approx(120.0)  # 60 dakika × 2.0
    assert last["ts"] > first["ts"]


def test_funding_is_reported_with_its_distance_from_the_monthly_average(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    funding = client.get(f"/api/v1/market/{SYMBOL}/orderflow").json()["funding"]

    assert funding["last_rate"] == pytest.approx(0.0004)
    assert funding["average_30d"] is not None
    assert funding["zscore"] > 2  # olağandışı yüksek: kalabalık uyarısı
    assert funding["next_funding_time"] is not None


def test_open_interest_reports_the_daily_change(client: TestClient, settings: Settings) -> None:
    _run(_seed(settings))
    oi = client.get(f"/api/v1/market/{SYMBOL}/orderflow").json()["open_interest"]

    assert oi["latest"] == pytest.approx(1287.0)
    assert oi["change_24h"] == pytest.approx(287 / 1000.0, rel=0.01)


def test_the_three_long_short_ratios_are_returned_once_each(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    rows = client.get(f"/api/v1/market/{SYMBOL}/orderflow").json()["long_short"]

    assert [row["kind"] for row in rows] == ["global_account", "top_account", "top_position"]


def test_coverage_ratio_shows_how_much_of_the_window_was_listened_to(
    client: TestClient, settings: Settings
) -> None:
    _run(_seed(settings))
    body = client.get(f"/api/v1/market/{SYMBOL}/orderflow", params={"minutes": 120}).json()

    # 60 dakika tam dinlenmiş, pencere 120 dakika → yarısı.
    assert body["coverage_ratio"] == pytest.approx(0.5)


def test_liquidations_are_listed_with_their_side(client: TestClient, settings: Settings) -> None:
    _run(_seed(settings))
    rows = client.get(f"/api/v1/market/{SYMBOL}/orderflow").json()["liquidations"]

    assert [row["side"] for row in rows] == ["short"]
    assert rows[0]["usd"] == pytest.approx(1200.0)


def test_an_empty_database_answers_with_empty_lists(client: TestClient) -> None:
    body = client.get(f"/api/v1/market/{SYMBOL}/orderflow").json()

    assert body["minutes"] == []
    assert body["liquidations"] == []
    assert body["funding"]["last_rate"] is None
    assert body["open_interest"]["latest"] is None
    assert body["coverage_ratio"] == 0.0


def test_unknown_symbols_are_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/market/DOGEUSDT/orderflow").status_code == 404
