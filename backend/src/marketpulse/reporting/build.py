"""Rapor gövdesi (ARCHITECTURE.md §10).

`build_report()` çıktısı `predictions.report_json` alanına yazılır ve arayüzde olduğu gibi
gösterilir. Tüm cümleler `templates.py` şablonlarından gelir: serbest metin üreten kod yoktur
(K4). Böylece rapor test edilebilir ve sayıyla çelişen bir cümle üretmesi mümkün değildir.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

from marketpulse.core.types import Horizon
from marketpulse.ensemble.combine import EnsembleResult
from marketpulse.ensemble.confidence import ConfidenceReading
from marketpulse.ensemble.expected_range import ExpectedRange
from marketpulse.reporting import counter_argument
from marketpulse.reporting.templates import CONFIDENCE_TR, module_tr, render
from marketpulse.signals.base import SignalResult

MAX_REASONS: Final = 6
MIN_REASONS: Final = 3


def build_report(
    *,
    symbol: str,
    horizon: Horizon,
    results: Sequence[SignalResult],
    ensemble: EnsembleResult,
    confidence: ConfidenceReading,
    expected: ExpectedRange | None,
) -> dict[str, Any]:
    """Tahmin raporunu sözlük olarak üretir (JSON'a olduğu gibi yazılır)."""
    reasons = _reasons(results, ensemble)
    counter = counter_argument.build(results, ensemble.effective_weights, p_up=ensemble.p_up)
    report: dict[str, Any] = {
        "headline": render(
            "headline",
            symbol=_short_symbol(symbol),
            horizon_tr=horizon.label_tr,
            p_up_pct=f"{ensemble.p_up * 100:.0f}",
            confidence_tr=CONFIDENCE_TR[confidence.label],
        ),
        "veto": None,
        "conflict": ensemble.conflict.active,
        "reasons": reasons,
        "counter_argument": counter.text,
        "expected_range": (
            None if expected is None else {"low": expected.low, "high": expected.high}
        ),
        "confidence": {"value": round(confidence.value, 3), "label": confidence.label},
        "data_coverage": {result.module: round(result.coverage, 3) for result in results},
        "missing": list(ensemble.missing_modules),
    }
    if ensemble.conflict.active:
        reasons.insert(0, _conflict_reason(ensemble))
    return report


def _reasons(results: Sequence[SignalResult], ensemble: EnsembleResult) -> list[dict[str, Any]]:
    """Katkısı en büyük modüllerin gerekçe maddeleri, katkı sırasına göre."""
    ordered = sorted(
        (result for result in results if result.module in ensemble.effective_weights),
        key=lambda result: abs(ensemble.contributions.get(result.module, 0.0)),
        reverse=True,
    )
    total = sum(abs(value) for value in ensemble.contributions.values())
    lines: list[dict[str, Any]] = []
    for result in ordered:
        # Pay: bu modül toplam katkının yüzde kaçını taşıyor (arayüzde okunabilir olsun diye).
        share = abs(ensemble.contributions.get(result.module, 0.0)) / total if total > 0 else 0.0
        for text in result.rationale:
            lines.append(
                {
                    "module": result.module,
                    "text": render("reason_line", module_tr=module_tr(result.module), text=text),
                    "weight": round(share, 3),
                }
            )
            if len(lines) >= MAX_REASONS:
                return lines
    return lines


def _conflict_reason(ensemble: EnsembleResult) -> dict[str, Any]:
    reading = ensemble.conflict
    up = module_tr(reading.positive[0]) if reading.positive else "bir modül"
    down = module_tr(reading.negative[0]) if reading.negative else "başka bir modül"
    return {
        "module": "ensemble",
        "text": render("conflict", module_a=up, dir_a="yukarı", module_b=down, dir_b="aşağı"),
        "weight": 1.0,
    }


def module_coverage(results: Sequence[SignalResult]) -> Mapping[str, float]:
    return {result.module: result.coverage for result in results}


def _short_symbol(symbol: str) -> str:
    """BTCUSDT → BTC: başlıkta kotasyon para birimi gürültüdür."""
    for quote in ("USDT", "USDC", "BUSD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)]
    return symbol
