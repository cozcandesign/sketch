"""Ensemble: log-odds birleştirme, ağırlık yeniden dağıtımı, çelişki, güven, beklenen aralık."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from marketpulse.core.types import Horizon, Interval
from marketpulse.ensemble import confidence, conflict, expected_range
from marketpulse.ensemble.combine import DEFAULT_K, P_MAX, P_MIN, combine, sigmoid
from marketpulse.ensemble.weights import MODULES, load_default_weights
from marketpulse.features.snapshot import FeatureSnapshot, coverage_key
from marketpulse.signals.base import ModuleName, SignalResult
from marketpulse.storage import SqliteRepository, make_engine

AS_OF = datetime(2026, 3, 1, tzinfo=UTC)
EVEN_WEIGHTS = dict.fromkeys(MODULES, 0.2)


def signal(
    module: ModuleName, score: float, *, confidence_value: float = 1.0, coverage: float = 1.0
) -> SignalResult:
    return SignalResult(
        module=module,
        score=score,
        confidence=confidence_value,
        coverage=coverage,
        data_as_of=AS_OF,
    )


def test_a_single_module_maps_its_score_through_the_logistic() -> None:
    result = combine([signal("technical", 0.5)], {"technical": 1.0}, horizon=Horizon.H1H)
    assert result.p_up == pytest.approx(sigmoid(DEFAULT_K * 0.5))
    assert result.combined_score == pytest.approx(0.5)
    assert result.used_modules == ("technical",)


def test_probability_is_clipped_to_the_modesty_band() -> None:
    """K19: kalibrasyon kanıtlanana kadar [0.10, 0.90] dışına çıkılmaz."""
    # Varsayılan k=2 ile en uç skor bile %88'de kalır; kırpma daha büyük k'de devreye girer.
    for k in (DEFAULT_K, 10.0):
        up = combine([signal("technical", 1.0)], {"technical": 1.0}, horizon=Horizon.H1H, k=k)
        down = combine([signal("technical", -1.0)], {"technical": 1.0}, horizon=Horizon.H1H, k=k)
        assert P_MIN <= down.p_up < 0.5 < up.p_up <= P_MAX
    strong = combine([signal("technical", 1.0)], {"technical": 1.0}, horizon=Horizon.H1H, k=10.0)
    assert strong.p_up == pytest.approx(P_MAX)


def test_modules_without_data_have_their_weight_redistributed() -> None:
    """Veri yok diyen modül ağırlığı çalışanlara dağılır: formülün kendisi yapar."""
    results = [
        signal("technical", 0.6),
        SignalResult(module="orderflow", score=0.0, confidence=0.0, coverage=0.0),
        SignalResult(module="news", score=0.0, confidence=0.0, coverage=0.0),
    ]
    result = combine(results, EVEN_WEIGHTS, horizon=Horizon.H1H)
    assert result.used_modules == ("technical",)
    assert "orderflow" in result.missing_modules
    assert result.combined_score == pytest.approx(0.6)  # tek çalışan modül tam ağırlık taşır


def test_a_low_confidence_module_counts_less_than_a_confident_one() -> None:
    results = [signal("technical", 1.0, confidence_value=0.2), signal("macro", -1.0)]
    result = combine(results, EVEN_WEIGHTS, horizon=Horizon.H1H)
    assert result.combined_score < 0  # güvenli olan ağır basar
    assert result.effective_weights["technical"] < result.effective_weights["macro"]


def test_without_any_usable_module_the_answer_is_fifty_fifty() -> None:
    results = [SignalResult(module=m, score=0.0, confidence=0.0, coverage=0.0) for m in MODULES]
    result = combine(results, EVEN_WEIGHTS, horizon=Horizon.H1H)
    assert result.p_up == 0.5
    assert not result.has_signal
    assert set(result.missing_modules) == set(MODULES)


def test_opposing_modules_raise_a_conflict_and_pull_the_probability_to_the_middle() -> None:
    results = [signal("technical", 0.8), signal("macro", -0.6)]
    weights = {"technical": 0.5, "macro": 0.5}
    result = combine(results, weights, horizon=Horizon.H4H)
    assert result.conflict.active
    assert result.conflict.positive == ("technical",)
    assert result.conflict.negative == ("macro",)
    plain = sigmoid(result.log_odds)
    assert abs(result.p_up - 0.5) < abs(plain - 0.5)


def test_agreeing_modules_do_not_raise_a_conflict() -> None:
    results = [signal("technical", 0.6), signal("macro", 0.5)]
    result = combine(results, {"technical": 0.5, "macro": 0.5}, horizon=Horizon.H4H)
    assert not result.conflict.active


def test_weak_opposite_scores_are_not_a_conflict() -> None:
    """|skor| < 0.3 olan modül "yön söylemiyor" sayılır; gürültü çelişki üretmez."""
    results = [signal("technical", 0.5), signal("macro", -0.1)]
    result = combine(results, {"technical": 0.5, "macro": 0.5}, horizon=Horizon.H4H)
    assert not result.conflict.active


def test_conflict_pull_is_thirty_percent_towards_half() -> None:
    assert conflict.apply(1.0) == pytest.approx(0.85)
    assert conflict.apply(0.0) == pytest.approx(0.15)
    assert conflict.apply(0.5) == pytest.approx(0.5)


def test_confidence_falls_when_modules_disagree() -> None:
    agreeing = [signal("technical", 0.5), signal("macro", 0.5)]
    disagreeing = [signal("technical", 0.5), signal("macro", -0.5)]
    weights = {"technical": 0.5, "macro": 0.5}
    high = confidence.evaluate(agreeing, weights)
    low = confidence.evaluate(disagreeing, weights)
    assert low.value < high.value


def test_confidence_falls_when_coverage_is_partial() -> None:
    full = confidence.evaluate([signal("technical", 0.5)], {"technical": 1.0})
    partial = confidence.evaluate([signal("technical", 0.5, coverage=0.3)], {"technical": 1.0})
    assert partial.value < full.value


def test_conflict_or_veto_caps_the_confidence_label_at_low() -> None:
    results = [signal("technical", 0.5), signal("macro", 0.5)]
    weights = {"technical": 0.5, "macro": 0.5}
    assert confidence.evaluate(results, weights).label in {"mid", "high"}
    assert confidence.evaluate(results, weights, conflict_active=True).label == "low"
    assert confidence.evaluate(results, weights, veto_active=True).label == "low"


def test_confidence_is_zero_without_usable_modules() -> None:
    reading = confidence.evaluate([], {})
    assert reading.value == 0.0
    assert reading.label == "low"


def test_high_volatility_and_a_calendar_event_lower_the_confidence() -> None:
    results = [signal("technical", 0.5)]
    weights = {"technical": 1.0}
    calm = confidence.evaluate(results, weights)
    wild = confidence.evaluate(results, weights, high_volatility=True)
    busy = confidence.evaluate(results, weights, calendar_event_near=True)
    assert wild.value < calm.value
    assert busy.value < calm.value


def test_default_weights_cover_every_horizon_and_module() -> None:
    table = load_default_weights()
    assert set(table) == set(Horizon)
    for horizon, weights in table.items():
        assert set(weights) == set(MODULES), horizon
        assert sum(weights.values()) == pytest.approx(1.0)


def test_broken_weight_files_are_rejected_loudly(tmp_path: Path) -> None:
    path = tmp_path / "weights.yaml"
    path.write_text("version: 1\nhorizons:\n  30m:\n    technical: 1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ağırlığı olmayan modül"):
        load_default_weights(path)


def snapshot_with_atr(prices: list[float], interval: Interval) -> FeatureSnapshot:
    close_times = [AS_OF - (len(prices) - 1 - i) * interval.length for i in range(len(prices))]
    close = pd.Series(prices, dtype="float64")
    frame = pd.DataFrame(
        {
            "open_time": [t - interval.length for t in close_times],
            "open": close.to_numpy(),
            "high": (close * 1.01).to_numpy(),
            "low": (close * 0.99).to_numpy(),
            "close": close.to_numpy(),
            "volume": [10.0] * len(prices),
            "quote_volume": [100.0] * len(prices),
            "trades": [1] * len(prices),
            "taker_buy_base": [5.0] * len(prices),
        },
        index=pd.DatetimeIndex(close_times, name="close_time"),
    )
    return FeatureSnapshot(
        symbol="BTCUSDT",
        as_of=AS_OF,
        candles={interval: frame},
        coverage={coverage_key(interval): 1.0},
        freshness={coverage_key(interval): 0.0},
        price=prices[-1],
    )


def test_expected_range_brackets_the_current_price() -> None:
    prices = [100.0 + (i % 7) for i in range(400)]
    snapshot = snapshot_with_atr(prices, Interval.M15)
    result = expected_range.estimate(snapshot, Horizon.H1H)
    assert result is not None
    assert result.low < snapshot.price < result.high
    assert result.source == "atr+realized"


def test_atr_is_scaled_by_the_square_root_of_the_horizon_length() -> None:
    """Volatilite zamanın kareköküyle büyür: 15 dk ATR'si 1 saatlik ufukta 2 katına çıkar."""
    assert expected_range.scale_to_horizon(10.0, Horizon.H1H) == pytest.approx(20.0)  # 4 adım
    assert expected_range.scale_to_horizon(10.0, Horizon.H4H) == pytest.approx(20.0)  # 4 adım
    assert expected_range.scale_to_horizon(10.0, Horizon.H30M) == pytest.approx(
        10.0 * 6**0.5
    )  # 30 dk / 5 dk


def test_expected_range_uses_atr_alone_when_history_is_short() -> None:
    """30 örnekten az gerçekleşmiş getiri varsa dağılım hesaplanmaz; yalnız ATR kullanılır."""
    prices = [100.0 + (i % 5) for i in range(25)]
    result = expected_range.estimate(snapshot_with_atr(prices, Interval.M15), Horizon.H1H)
    assert result is not None
    assert result.source == "atr"


def test_expected_range_widens_in_a_volatility_expansion() -> None:
    prices = [100.0 + (i % 5) for i in range(200)]
    snapshot = snapshot_with_atr(prices, Interval.M15)
    normal = expected_range.estimate(snapshot, Horizon.H1H)
    expanded = expected_range.estimate(snapshot, Horizon.H1H, expansion=True)
    assert normal is not None
    assert expanded is not None
    assert expanded.width == pytest.approx(normal.width * 1.5)


def test_expected_range_is_none_without_candles() -> None:
    empty = FeatureSnapshot(
        symbol="BTCUSDT", as_of=AS_OF, candles={}, coverage={}, freshness={}, price=None
    )
    assert expected_range.estimate(empty, Horizon.H1H) is None


async def test_weights_are_seeded_once_and_never_overwritten() -> None:
    """K3: sistem ağırlıkları kendiliğinden değiştirmez; tohum yalnızca boş tabloya atılır."""
    repo = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repo.create_all()
    table = load_default_weights()

    written = await repo.seed_weights(table, valid_from=AS_OF)
    assert written == len(Horizon) * len(MODULES)
    assert await repo.get_weights(Horizon.H4H) == pytest.approx(table[Horizon.H4H])

    # kullanıcı onayıyla değişmiş bir ağırlık, ikinci tohumlamada ezilmemeli
    again = await repo.seed_weights(table, valid_from=AS_OF)
    assert again == 0
    await repo.close()


async def test_weights_are_empty_before_seeding() -> None:
    repo = SqliteRepository(make_engine("sqlite+aiosqlite:///:memory:"))
    await repo.create_all()
    assert await repo.get_weights(Horizon.H1H) == {}
    assert await repo.count_weights() == 0
    await repo.close()


def test_weight_mass_reports_how_much_of_the_evidence_base_is_present() -> None:
    """Faz 2'de yalnız teknik modül var: kanıt tabanının küçük bir kısmı."""
    results = [
        signal("technical", 0.6),
        SignalResult(module="orderflow", score=0.0, confidence=0.0, coverage=0.0),
        SignalResult(module="news", score=0.0, confidence=0.0, coverage=0.0),
        SignalResult(module="macro", score=0.0, confidence=0.0, coverage=0.0),
        SignalResult(module="sentiment", score=0.0, confidence=0.0, coverage=0.0),
    ]
    weights = load_default_weights()[Horizon.H1H]
    result = combine(results, weights, horizon=Horizon.H1H)
    assert result.weight_mass == pytest.approx(weights["technical"])
    assert result.combined_score == pytest.approx(0.6)  # skor yine yeniden dağıtılır


def test_a_single_module_does_not_produce_high_confidence() -> None:
    """Beş modülün dördü yokken "yüksek güven" yanıltıcı olurdu."""
    results = [signal("technical", 0.6)]
    weights = load_default_weights()[Horizon.H1H]
    result = combine(results, weights, horizon=Horizon.H1H)
    reading = confidence.evaluate(results, result.effective_weights, breadth=result.weight_mass)
    assert reading.label == "low"
    assert reading.parts["breadth"] == pytest.approx(weights["technical"])


def test_full_evidence_base_allows_high_confidence() -> None:
    results = [signal(module, 0.5) for module in MODULES]
    weights = load_default_weights()[Horizon.H1H]
    result = combine(results, weights, horizon=Horizon.H1H)
    reading = confidence.evaluate(results, result.effective_weights, breadth=result.weight_mass)
    assert reading.label in {"mid", "high"}
