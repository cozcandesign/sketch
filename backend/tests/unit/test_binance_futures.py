"""Futures REST istemcisi: yanıt ayrıştırma ve uç nokta parametreleri (ağ yok, respx)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from marketpulse.collectors.binance_client import BinanceClient
from marketpulse.collectors.binance_futures import (
    FUNDING_RATE_PATH,
    GLOBAL_LONG_SHORT_PATH,
    MAX_DATA_LIMIT,
    OPEN_INTEREST_HIST_PATH,
    OPEN_INTEREST_PATH,
    PREMIUM_INDEX_PATH,
    TAKER_VOLUME_PATH,
    TOP_POSITION_PATH,
    FuturesClient,
)
from marketpulse.core.clock import FakeClock
from marketpulse.engine.ratelimit import RateLimiter
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
NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def client() -> FuturesClient:
    limiter = RateLimiter(FakeClock(NOW), name="binance_futures")
    return FuturesClient(BinanceClient(BASE, limiter, sleep=_no_sleep))


async def _no_sleep(_seconds: float) -> None:
    return None


@respx.mock
async def test_funding_history_is_parsed_with_utc_times(client: FuturesClient) -> None:
    route = respx.get(f"{BASE}{FUNDING_RATE_PATH}").mock(
        return_value=httpx.Response(200, json=funding_rate_rows(count=2))
    )
    rows = await client.funding_history("BTCUSDT")

    assert route.called
    assert len(rows) == 2
    assert rows[0].symbol == "BTCUSDT"
    assert rows[0].funding_time == FUTURES_T0
    assert rows[0].rate == pytest.approx(0.0001)
    assert rows[1].funding_time == FUTURES_T0 + timedelta(hours=8)
    assert rows[0].mark_price == pytest.approx(60000.0)


@respx.mock
async def test_funding_history_sends_the_start_time(client: FuturesClient) -> None:
    route = respx.get(f"{BASE}{FUNDING_RATE_PATH}").mock(return_value=httpx.Response(200, json=[]))
    await client.funding_history("BTCUSDT", start=FUTURES_T0)

    assert route.calls.last.request.url.params["startTime"] == str(
        int(FUTURES_T0.timestamp() * 1000)
    )


@respx.mock
async def test_premium_index_gives_the_live_funding_state(client: FuturesClient) -> None:
    respx.get(f"{BASE}{PREMIUM_INDEX_PATH}").mock(
        return_value=httpx.Response(200, json=premium_index())
    )
    live = await client.funding_live("BTCUSDT", now=NOW)

    assert live.last_rate == pytest.approx(0.000125)
    assert live.next_funding_time == FUTURES_T0 + timedelta(hours=8)
    assert live.mark_price == pytest.approx(60125.3)
    assert live.index_price == pytest.approx(60110.1)


@respx.mock
async def test_open_interest_live_and_history_are_tagged_by_source(
    client: FuturesClient,
) -> None:
    respx.get(f"{BASE}{OPEN_INTEREST_PATH}").mock(
        return_value=httpx.Response(200, json=open_interest_live())
    )
    respx.get(f"{BASE}{OPEN_INTEREST_HIST_PATH}").mock(
        return_value=httpx.Response(200, json=open_interest_hist_rows(count=2))
    )

    live = await client.open_interest_live("BTCUSDT", now=NOW)
    history = await client.open_interest_history("BTCUSDT")

    assert live.source == "live"
    assert live.oi == pytest.approx(76543.21)
    assert live.oi_value_usd is None  # canlı uç değer vermez: uydurulmaz
    assert [point.source for point in history] == ["hist", "hist"]
    assert history[0].oi_value_usd == pytest.approx(76000 * 60000)


@respx.mock
async def test_long_short_ratios_carry_their_kind(client: FuturesClient) -> None:
    respx.get(f"{BASE}{GLOBAL_LONG_SHORT_PATH}").mock(
        return_value=httpx.Response(200, json=long_short_rows(count=1))
    )
    respx.get(f"{BASE}{TOP_POSITION_PATH}").mock(
        return_value=httpx.Response(200, json=long_short_rows(count=1))
    )

    global_rows = await client.long_short("BTCUSDT", "global_account")
    top_rows = await client.long_short("BTCUSDT", "top_position")

    assert global_rows[0].kind == "global_account"
    assert global_rows[0].long_ratio == pytest.approx(0.60)
    assert global_rows[0].short_ratio == pytest.approx(0.40)
    assert global_rows[0].ratio == pytest.approx(1.50)
    assert top_rows[0].kind == "top_position"


@respx.mock
async def test_taker_volume_takes_the_symbol_from_the_request(client: FuturesClient) -> None:
    """Taker yanıtında sembol alanı yok; istekteki sembol kullanılır."""
    respx.get(f"{BASE}{TAKER_VOLUME_PATH}").mock(
        return_value=httpx.Response(200, json=taker_volume_rows(count=2))
    )
    rows = await client.taker_volume("ETHUSDT")

    assert {row.symbol for row in rows} == {"ETHUSDT"}
    assert rows[0].buy_vol == pytest.approx(380.0)
    assert rows[0].sell_vol == pytest.approx(310.0)
    assert rows[0].ratio == pytest.approx(1.20)


@respx.mock
async def test_data_endpoints_cap_the_limit_at_five_hundred(client: FuturesClient) -> None:
    """`/futures/data/*` en fazla 500 satır verir; daha büyük istek reddedilmesin diye kırpılır."""
    route = respx.get(f"{BASE}{OPEN_INTEREST_HIST_PATH}").mock(
        return_value=httpx.Response(200, json=[])
    )
    await client.open_interest_history("BTCUSDT", limit=5000)

    assert route.calls.last.request.url.params["limit"] == str(MAX_DATA_LIMIT)


@respx.mock
async def test_an_empty_response_is_not_an_error(client: FuturesClient) -> None:
    """Yeni sembolde geçmiş boş olabilir; boş liste dönmeli, istisna değil."""
    respx.get(f"{BASE}{FUNDING_RATE_PATH}").mock(return_value=httpx.Response(200, json=[]))
    assert await client.funding_history("BTCUSDT") == []
