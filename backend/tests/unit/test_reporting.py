"""Rapor üretimi: başlık, gerekçeler, karşıt argüman, çelişki ve yasak kelime taraması."""

from datetime import UTC, datetime

import pytest

from marketpulse.core.types import Horizon
from marketpulse.ensemble.combine import combine
from marketpulse.ensemble.confidence import evaluate
from marketpulse.ensemble.expected_range import ExpectedRange
from marketpulse.reporting import counter_argument
from marketpulse.reporting.banned_words import find_banned
from marketpulse.reporting.build import build_report
from marketpulse.reporting.templates import TEMPLATES
from marketpulse.signals.base import ModuleName, SignalResult

AS_OF = datetime(2026, 3, 1, tzinfo=UTC)


def signal(
    module: ModuleName,
    score: float,
    *,
    components: dict[str, float] | None = None,
    rationale: tuple[str, ...] = ("gerekçe cümlesi",),
    coverage: float = 1.0,
    confidence_value: float = 0.8,
) -> SignalResult:
    return SignalResult(
        module=module,
        score=score,
        confidence=confidence_value,
        coverage=coverage,
        components=components or {"trend": score},
        rationale=rationale,
        data_as_of=AS_OF,
    )


def report_for(
    results: list[SignalResult], weights: dict[str, float], horizon: Horizon = Horizon.H4H
) -> dict[str, object]:
    ensemble = combine(results, weights, horizon=horizon)
    reading = evaluate(
        results,
        ensemble.effective_weights,
        conflict_active=ensemble.conflict.active,
        breadth=ensemble.weight_mass,
    )
    return build_report(
        symbol="BTCUSDT",
        horizon=horizon,
        results=results,
        ensemble=ensemble,
        confidence=reading,
        expected=ExpectedRange(low=60000.0, high=64000.0, source="atr"),
    )


def test_headline_names_the_symbol_horizon_probability_and_confidence() -> None:
    report = report_for([signal("technical", 0.5)], {"technical": 1.0})
    headline = report["headline"]
    assert isinstance(headline, str)
    assert headline.startswith("BTC · 4 saat · Yukarı olasılığı %")
    assert "Güven:" in headline


def test_reasons_come_from_the_module_rationale_and_carry_the_module_name() -> None:
    results = [signal("technical", 0.6, rationale=("EMA dizilimi yukarı yönlü",))]
    report = report_for(results, {"technical": 1.0})
    reasons = report["reasons"]
    assert isinstance(reasons, list)
    assert reasons[0]["module"] == "technical"
    assert reasons[0]["text"] == "teknik: EMA dizilimi yukarı yönlü"


def test_reasons_are_ordered_by_contribution() -> None:
    strong = signal("technical", 0.9, rationale=("güçlü madde",))
    weak = signal("macro", 0.1, rationale=("zayıf madde",), confidence_value=0.1)
    report = report_for([weak, strong], {"technical": 0.5, "macro": 0.5})
    reasons = report["reasons"]
    assert isinstance(reasons, list)
    assert reasons[0]["text"] == "teknik: güçlü madde"


def test_a_conflict_is_the_first_line_of_the_report() -> None:
    results = [
        signal("technical", 0.8, rationale=("teknik madde",)),
        signal("macro", -0.7, rationale=("makro madde",)),
    ]
    report = report_for(results, {"technical": 0.5, "macro": 0.5})
    reasons = report["reasons"]
    assert isinstance(reasons, list)
    assert report["conflict"] is True
    assert reasons[0]["module"] == "ensemble"
    assert "Çelişkili sinyal" in reasons[0]["text"]


def test_missing_modules_are_listed_and_coverage_is_reported() -> None:
    results = [
        signal("technical", 0.5),
        SignalResult(module="news", score=0.0, confidence=0.0, coverage=0.0),
    ]
    report = report_for(results, {"technical": 0.5, "news": 0.5})
    assert report["missing"] == ["news"]
    assert report["data_coverage"] == {"technical": 1.0, "news": 0.0}


def test_the_counter_argument_names_the_strongest_opposing_component() -> None:
    results = [
        signal("technical", 0.6, components={"trend": 0.9, "sr": -0.7}),
    ]
    report = report_for(results, {"technical": 1.0})
    counter = report["counter_argument"]
    assert isinstance(counter, str)
    assert "destek/direnç" in counter
    assert "-0.70" in counter


def test_the_counter_argument_falls_back_to_the_volatility_squeeze() -> None:
    results = [signal("technical", 0.6, components={"trend": 0.9, "vol_regime": -0.95})]
    result = counter_argument.build(results, {"technical": 1.0}, p_up=0.7)
    assert result.source == "squeeze"
    assert "sıkışmış" in result.text


def test_the_counter_argument_falls_back_to_low_coverage() -> None:
    results = [signal("technical", 0.6, components={"trend": 0.9}, coverage=0.3)]
    result = counter_argument.build(results, {"technical": 1.0}, p_up=0.7)
    assert result.source == "coverage"
    assert "%30" in result.text


def test_the_counter_argument_has_a_last_resort_template() -> None:
    results = [signal("technical", 0.6, components={"trend": 0.9})]
    result = counter_argument.build(results, {"technical": 1.0}, p_up=0.7)
    assert result.source == "default"
    assert result.text.startswith("Beni yanıltacak şey")


def test_a_downward_prediction_looks_for_upward_components() -> None:
    results = [signal("technical", -0.6, components={"trend": -0.9, "momentum": 0.8})]
    result = counter_argument.build(results, {"technical": 1.0}, p_up=0.3)
    assert result.source == "component"
    assert "momentum" in result.text


def test_every_report_field_is_free_of_banned_words() -> None:
    results = [
        signal("technical", 0.8, components={"trend": 0.9, "sr": -0.5}),
        signal("macro", -0.6),
    ]
    report = report_for(results, {"technical": 0.5, "macro": 0.5})
    texts = [report["headline"], report["counter_argument"]]
    reasons = report["reasons"]
    assert isinstance(reasons, list)
    texts.extend(reason["text"] for reason in reasons)
    for text in texts:
        assert isinstance(text, str)
        assert find_banned(text) == [], text


def test_no_template_contains_a_banned_word() -> None:
    for key, template in TEMPLATES.items():
        assert find_banned(template) == [], key


def test_the_expected_range_is_carried_into_the_report() -> None:
    report = report_for([signal("technical", 0.5)], {"technical": 1.0})
    assert report["expected_range"] == {"low": 60000.0, "high": 64000.0}


def test_a_report_without_any_module_still_renders() -> None:
    """Hiç veri yokken de rapor üretilebilmeli: "bilmiyorum" da bir cevaptır."""
    results = [SignalResult(module="technical", score=0.0, confidence=0.0, coverage=0.0)]
    ensemble = combine(results, {"technical": 1.0}, horizon=Horizon.H1H)
    reading = evaluate(results, ensemble.effective_weights)
    report = build_report(
        symbol="ETHUSDT",
        horizon=Horizon.H1H,
        results=results,
        ensemble=ensemble,
        confidence=reading,
        expected=None,
    )
    assert report["reasons"] == []
    assert report["expected_range"] is None
    assert report["missing"] == ["technical"]
    headline = report["headline"]
    assert isinstance(headline, str)
    assert "%50" in headline


@pytest.mark.parametrize("horizon", list(Horizon))
def test_the_headline_uses_the_turkish_horizon_label(horizon: Horizon) -> None:
    report = report_for([signal("technical", 0.4)], {"technical": 1.0}, horizon)
    headline = report["headline"]
    assert isinstance(headline, str)
    assert horizon.label_tr in headline


def test_reason_weights_are_shares_that_sum_to_one_per_module() -> None:
    """Arayüzde "bu madde katkının %kaçı" okunabilsin diye pay verilir, ham log-odds değil."""
    report = report_for([signal("technical", 0.6)], {"technical": 1.0})
    reasons = report["reasons"]
    assert isinstance(reasons, list)
    assert reasons[0]["weight"] == pytest.approx(1.0)
