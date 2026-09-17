"""Order flow modülü: her bileşen için beklenen işaret, eksik veri ve yasak kelime denetimi."""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from marketpulse.core.types import Horizon, Interval
from marketpulse.features.snapshot import FeatureSnapshot, coverage_key, dataset_frame
from marketpulse.reporting.banned_words import find_banned
from marketpulse.signals.orderflow import COMPONENT_WEIGHTS, OrderflowModule

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
HORIZON = Horizon.H1H  # ana TF 15m, pencere 1 saat
SYMBOL = "BTCUSDT"


def candle_frame(prices: list[float], interval: Interval = Interval.M15) -> pd.DataFrame:
    times = [AS_OF - (len(prices) - 1 - i) * interval.length for i in range(len(prices))]
    close = pd.Series(prices, dtype="float64")
    return pd.DataFrame(
        {
            "open_time": [t - interval.length for t in times],
            "open": close.to_numpy(),
            "high": (close * 1.002).to_numpy(),
            "low": (close * 0.998).to_numpy(),
            "close": close.to_numpy(),
            "volume": [50.0] * len(prices),
            "quote_volume": [1000.0] * len(prices),
            "trades": [10] * len(prices),
            "taker_buy_base": [25.0] * len(prices),
        },
        index=pd.DatetimeIndex(times, name="close_time"),
    )


def flow_frame(rows: list[dict[str, float]], *, minutes: int) -> pd.DataFrame:
    data = []
    for index, row in enumerate(rows):
        ts = AS_OF - (minutes - 1 - index) * timedelta(minutes=1)
        data.append({"ts": ts, **row})
    return dataset_frame("orderflow_1m", data)


def build_snapshot(
    *,
    prices: list[float] | None = None,
    flow: pd.DataFrame | None = None,
    funding: list[float] | None = None,
    funding_live: float | None = None,
    open_interest: list[float] | None = None,
    taker: list[tuple[float, float]] | None = None,
) -> FeatureSnapshot:
    datasets: dict[str, pd.DataFrame] = {}
    if taker is not None:
        datasets["taker_volume"] = dataset_frame(
            "taker_volume",
            [
                {
                    "ts": AS_OF - timedelta(minutes=5 * (len(taker) - 1 - i)),
                    "buy_vol": buy,
                    "sell_vol": sell,
                    "ratio": buy / sell if sell else 0.0,
                }
                for i, (buy, sell) in enumerate(taker)
            ],
        )
    if funding is not None:
        datasets["funding"] = dataset_frame(
            "funding",
            [
                {"ts": AS_OF - timedelta(hours=8 * (len(funding) - 1 - i)), "rate": rate}
                for i, rate in enumerate(funding)
            ],
        )
    if funding_live is not None:
        datasets["funding_live"] = dataset_frame(
            "funding_live", [{"ts": AS_OF, "last_rate": funding_live}]
        )
    if open_interest is not None:
        datasets["open_interest"] = dataset_frame(
            "open_interest",
            [
                {
                    "ts": AS_OF - timedelta(minutes=5 * (len(open_interest) - 1 - i)),
                    "oi": value,
                    "source": "hist",
                }
                for i, value in enumerate(open_interest)
            ],
        )
    if flow is not None:
        datasets["orderflow_1m"] = flow
    candles = {Interval.M15: candle_frame(prices or [100.0] * 60)}
    return FeatureSnapshot(
        symbol=SYMBOL,
        as_of=AS_OF,
        candles=candles,
        coverage={coverage_key(Interval.M15): 1.0},
        freshness={coverage_key(Interval.M15): 0.0},
        price=(prices or [100.0])[-1],
        datasets=datasets,
    )


def steady_flow(minutes: int = 120, **overrides: float) -> pd.DataFrame:
    row = {
        "buy_vol": 10.0,
        "sell_vol": 10.0,
        "cvd_delta": 0.0,
        "trade_count": 20,
        "liq_long_usd": 0.0,
        "liq_short_usd": 0.0,
        "liq_count": 0,
        "coverage_seconds": 60.0,
        **overrides,
    }
    return flow_frame([dict(row) for _ in range(minutes)], minutes=minutes)


def compute(snapshot: FeatureSnapshot) -> object:
    return OrderflowModule().compute(snapshot, HORIZON)


# --- funding ---


def test_crowded_longs_push_the_score_down() -> None:
    """Funding uzun süredir normalken birden yükselirse long tarafı kalabalıktır: ters sinyal."""
    history = [0.0001] * 20 + [0.0009]
    result = compute(build_snapshot(funding=history, funding_live=0.0009, flow=steady_flow()))
    assert result.components["funding_dev"] < 0


def test_crowded_shorts_push_the_score_up() -> None:
    history = [0.0001] * 20 + [-0.0009]
    result = compute(build_snapshot(funding=history, funding_live=-0.0009, flow=steady_flow()))
    assert result.components["funding_dev"] > 0


def test_ordinary_funding_is_neutral() -> None:
    """Dağılımın ortasındaki bir funding oranı kalabalık bilgisi taşımaz."""
    history = [0.00005, 0.00015] * 10  # ortalama 0.0001
    result = compute(build_snapshot(funding=history, funding_live=0.0001, flow=steady_flow()))
    assert result.components["funding_dev"] == pytest.approx(0.0)


# --- açık pozisyon × fiyat ---


def rising(count: int, start: float, step: float) -> list[float]:
    return [start + step * i for i in range(count)]


def falling(count: int, start: float, step: float) -> list[float]:
    return [start - step * i for i in range(count)]


def test_open_interest_up_with_price_up_is_real_buying() -> None:
    result = compute(
        build_snapshot(
            prices=rising(60, 100.0, 0.2),
            open_interest=rising(60, 1000.0, 5.0),
            flow=steady_flow(),
        )
    )
    assert result.components["oi_price"] > 0


def test_open_interest_up_with_price_down_is_short_building() -> None:
    result = compute(
        build_snapshot(
            prices=falling(60, 100.0, 0.2),
            open_interest=rising(60, 1000.0, 5.0),
            flow=steady_flow(),
        )
    )
    assert result.components["oi_price"] < 0


def test_position_closing_states_are_weaker_than_new_positions() -> None:
    """OI düşerken fiyat hareketi pozisyon kapanışıdır: aynı büyüklükte ama yarı ağırlıkta."""
    opening = compute(
        build_snapshot(
            prices=rising(60, 100.0, 0.2),
            open_interest=rising(60, 1000.0, 5.0),
            flow=steady_flow(),
        )
    )
    closing = compute(
        build_snapshot(
            prices=rising(60, 100.0, 0.2),
            open_interest=falling(60, 1000.0, 5.0),
            flow=steady_flow(),
        )
    )
    assert 0 < closing.components["oi_price"] < opening.components["oi_price"]


# --- likidasyon ---


def test_short_liquidations_read_as_forced_buying() -> None:
    flow = steady_flow(minutes=200)
    flow.iloc[-5:, flow.columns.get_loc("liq_short_usd")] = 50_000.0
    result = compute(build_snapshot(flow=flow))
    assert result.components["liquidations"] > 0


def test_long_liquidations_read_as_forced_selling() -> None:
    flow = steady_flow(minutes=200)
    flow.iloc[-5:, flow.columns.get_loc("liq_long_usd")] = 50_000.0
    result = compute(build_snapshot(flow=flow))
    assert result.components["liquidations"] < 0


def test_an_unusually_large_liquidation_wave_flips_the_sign() -> None:
    """Olağanın 3 katını aşan dalga tükeniş sayılır; yön tersine döner."""
    flow = steady_flow(minutes=200)
    flow.iloc[:, flow.columns.get_loc("liq_long_usd")] = 1_000.0  # olağan seviye
    flow.iloc[-10:, flow.columns.get_loc("liq_long_usd")] = 500_000.0  # dalga
    result = compute(build_snapshot(flow=flow))
    assert result.components["liquidations"] > 0  # long tasfiyesi ama ters çevrildi


def test_no_liquidations_is_neutral_not_missing() -> None:
    result = compute(build_snapshot(flow=steady_flow()))
    assert result.components["liquidations"] == pytest.approx(0.0)


# --- order book ---


def test_a_bid_heavy_book_scores_positive() -> None:
    flow = steady_flow()
    flow.iloc[-5:, flow.columns.get_loc("top20_imbalance")] = 0.4
    result = compute(build_snapshot(flow=flow))
    assert result.components["book_imbalance"] > 0


def test_an_ask_heavy_book_scores_negative() -> None:
    flow = steady_flow()
    flow.iloc[-5:, flow.columns.get_loc("depth1pct_imbalance")] = -0.3
    result = compute(build_snapshot(flow=flow))
    assert result.components["book_imbalance"] < 0


# --- CVD ---


def test_buying_while_the_price_falls_is_accumulation() -> None:
    flow = steady_flow(minutes=120, cvd_delta=2.0, buy_vol=12.0, sell_vol=10.0)
    result = compute(build_snapshot(prices=falling(60, 100.0, 0.2), flow=flow))
    assert result.components["cvd"] > 0


def test_selling_while_the_price_rises_is_distribution() -> None:
    flow = steady_flow(minutes=120, cvd_delta=-2.0, buy_vol=10.0, sell_vol=12.0)
    result = compute(build_snapshot(prices=rising(60, 100.0, 0.2), flow=flow))
    assert result.components["cvd"] < 0


def test_flow_that_agrees_with_price_counts_for_less_than_divergence() -> None:
    aligned = compute(
        build_snapshot(
            prices=rising(60, 100.0, 0.2),
            flow=steady_flow(minutes=120, cvd_delta=2.0, buy_vol=12.0, sell_vol=10.0),
        )
    )
    diverging = compute(
        build_snapshot(
            prices=falling(60, 100.0, 0.2),
            flow=steady_flow(minutes=120, cvd_delta=2.0, buy_vol=12.0, sell_vol=10.0),
        )
    )
    assert aligned.components["cvd"] < diverging.components["cvd"]


# --- sözleşme ---


def test_without_any_order_flow_data_the_module_says_no_data() -> None:
    result = compute(build_snapshot())
    assert not result.has_data
    assert result.score == 0.0


def test_scores_and_components_stay_in_range() -> None:
    flow = steady_flow(minutes=200, cvd_delta=5.0, buy_vol=20.0, sell_vol=1.0)
    flow.iloc[-5:, flow.columns.get_loc("liq_short_usd")] = 900_000.0
    result = compute(
        build_snapshot(
            prices=rising(60, 100.0, 1.0),
            open_interest=rising(60, 1000.0, 50.0),
            funding=[0.0001] * 20 + [0.002],
            funding_live=0.002,
            flow=flow,
        )
    )
    assert -1.0 <= result.score <= 1.0
    for name, value in result.components.items():
        assert -1.0 <= value <= 1.0, name


def test_partial_coverage_lowers_the_confidence() -> None:
    """Dinlenmemiş saniyeler kapsamayı düşürür: eksik dakika "sakin piyasa" sayılmaz."""
    full = compute(build_snapshot(flow=steady_flow(minutes=120)))
    patchy = compute(build_snapshot(flow=steady_flow(minutes=120, coverage_seconds=6.0)))
    assert patchy.coverage < full.coverage
    assert patchy.confidence < full.confidence


def test_rationale_is_turkish_and_free_of_banned_words() -> None:
    flow = steady_flow(minutes=200)
    flow.iloc[-5:, flow.columns.get_loc("liq_short_usd")] = 50_000.0
    flow.iloc[-5:, flow.columns.get_loc("top20_imbalance")] = 0.3
    result = compute(
        build_snapshot(
            prices=rising(60, 100.0, 0.2),
            open_interest=rising(60, 1000.0, 5.0),
            funding=[0.0001] * 20 + [0.0008],
            funding_live=0.0008,
            flow=flow,
        )
    )
    assert result.rationale
    for line in result.rationale:
        assert find_banned(line) == [], line


def test_the_module_is_pure() -> None:
    snapshot = build_snapshot(flow=steady_flow(), funding=[0.0001] * 20, funding_live=0.0002)
    module = OrderflowModule()
    assert module.compute(snapshot, HORIZON) == module.compute(snapshot, HORIZON)


def test_component_weights_match_the_architecture_table() -> None:
    assert COMPONENT_WEIGHTS == {
        "funding_dev": 0.20,
        "oi_price": 0.30,
        "liquidations": 0.15,
        "book_imbalance": 0.15,
        "cvd": 0.20,
    }


class TestCvdFallsBackToTakerVolume:
    """WS işlem akışı susarsa CVD bileşeni REST yedeğinden hesaplanır (ARCHITECTURE §4, F3-12).

    Canlıda ölçüldü: futures `aggTrade` akışı hiç mesaj göndermiyor, aynı sunucudaki derinlik
    akışı çalışıyor. Yedek olmadan bileşen tamamen kayboluyordu.
    """

    def _score(self, snapshot: FeatureSnapshot) -> float | None:
        result = OrderflowModule().compute(snapshot, HORIZON)
        return result.components.get("cvd")

    def test_taker_volume_is_used_when_the_trade_stream_is_silent(self) -> None:
        # Dakika satırları var (derinlik yazıyor) ama işlem hacmi sıfır: akış susuyor.
        silent = steady_flow(120, buy_vol=0.0, sell_vol=0.0, cvd_delta=0.0, trade_count=0)
        snapshot = build_snapshot(
            prices=[100.0] * 60,
            flow=silent,
            taker=[(70.0, 30.0)] * 12,  # belirgin alış baskısı
        )

        score = self._score(snapshot)

        assert score is not None, "yedek kaynak varken bileşen kaybolmamalı"
        assert score > 0

    def test_the_websocket_wins_when_it_has_data(self) -> None:
        """Akış çalışıyorsa ince çözünürlüklü kaynak tercih edilir; yedek devreye girmez."""
        flowing = steady_flow(120, buy_vol=30.0, sell_vol=10.0, cvd_delta=20.0)
        snapshot = build_snapshot(
            prices=[100.0] * 60,
            flow=flowing,
            taker=[(10.0, 90.0)] * 12,  # yedek ters yönü söylerdi
        )

        score = self._score(snapshot)

        assert score is not None
        assert score > 0  # WS'in dediği yön

    def test_no_component_when_both_sources_are_empty(self) -> None:
        """İkisi de boşsa bileşen gerçekten "veri yok"tur; uydurma sayı üretilmez."""
        silent = steady_flow(120, buy_vol=0.0, sell_vol=0.0, cvd_delta=0.0, trade_count=0)
        snapshot = build_snapshot(prices=[100.0] * 60, flow=silent)

        assert self._score(snapshot) is None
