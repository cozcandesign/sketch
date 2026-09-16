"""`/calibration`: doğruluk metrikleri (Brier, kalibrasyon eğrisi, isabet)."""

from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from marketpulse.api.deps import get_clock, get_repo
from marketpulse.api.schemas.calibration import (
    CalibrationBinOut,
    CalibrationOut,
    DailyPointOut,
    HorizonSummaryOut,
    ModelSummaryOut,
    ModuleSummaryOut,
    SummaryOut,
)
from marketpulse.core.clock import Clock
from marketpulse.core.types import Horizon
from marketpulse.storage.models import ModuleResolvedRow, ResolvedRow
from marketpulse.storage.repository import Repository
from marketpulse.tracking import metrics

router = APIRouter(tags=["calibration"])

WINDOW_DAYS: dict[str, int | None] = {"7d": 7, "30d": 30, "90d": 90, "all": None}
MODEL_LABELS_TR: dict[str, str] = {
    "baseline-climatology-1": "Referans: taban oranı",
    "baseline-momentum-1": "Referans: son mum rengi",
    "ensemble-v0": "Canlı tahmin (modüller)",
}
MODULE_LABELS_TR: dict[str, str] = {
    "technical": "teknik",
    "orderflow": "order flow",
    "news": "haber",
    "macro": "makro",
    "sentiment": "duyarlılık",
}
BASELINE_VERSIONS = ("baseline-climatology-1", "baseline-momentum-1")


def _summary_fields(summary: metrics.MetricsSummary) -> dict[str, Any]:
    return {
        "n": summary.n,
        "brier": summary.brier,
        "brier_skill": summary.brier_skill,
        "base_rate": summary.base_rate,
        "hit_rate": summary.hit_rate,
        "hit_ci_low": summary.hit_ci.low if summary.hit_ci else None,
        "hit_ci_high": summary.hit_ci.high if summary.hit_ci else None,
        "beats_uninformed": summary.beats_uninformed,
    }


def _by_model(rows: list[ResolvedRow]) -> list[ModelSummaryOut]:
    versions = sorted({r.ensemble_version for r in rows})
    return [
        ModelSummaryOut(
            model_version=version,
            label_tr=MODEL_LABELS_TR.get(version, version),
            **_summary_fields(
                metrics.summarize([r for r in rows if r.ensemble_version == version])
            ),
        )
        for version in versions
    ]


def _by_horizon(rows: list[ResolvedRow]) -> list[HorizonSummaryOut]:
    result = []
    for horizon in Horizon:
        bucket = [r for r in rows if r.horizon is horizon]
        if not bucket:
            continue
        result.append(
            HorizonSummaryOut(
                horizon=horizon.value,
                label_tr=horizon.label_tr,
                **_summary_fields(metrics.summarize(bucket)),
            )
        )
    return result


def _by_module(
    module_rows: list[ModuleResolvedRow], reference: float | None
) -> list[ModuleSummaryOut]:
    """Modül isabeti; K26 gereği referans tahmincilerin en iyisiyle karşılaştırılır."""
    return [
        ModuleSummaryOut(
            module=summary.module,
            label_tr=MODULE_LABELS_TR.get(summary.module, summary.module),
            n=summary.n,
            skipped=summary.skipped,
            hit_rate=summary.hit_rate,
            hit_ci_low=summary.hit_ci.low if summary.hit_ci else None,
            hit_ci_high=summary.hit_ci.high if summary.hit_ci else None,
            beats_reference=summary.beats(reference),
            has_proof_sample=summary.has_proof_sample,
        )
        for summary in metrics.module_summaries(module_rows)
    ]


def _reference_hit_rate(rows: list[ResolvedRow]) -> float | None:
    """Referans tahmincilerin en iyisi: modülün aşması gereken çizgi."""
    return metrics.best_reference_hit_rate(
        [
            metrics.summarize([r for r in rows if r.ensemble_version == version])
            for version in BASELINE_VERSIONS
        ]
    )


@router.get("/calibration", response_model=CalibrationOut)
async def get_calibration(
    repo: Annotated[Repository, Depends(get_repo)],
    clock: Annotated[Clock, Depends(get_clock)],
    symbol: str | None = None,
    horizon: Horizon | None = None,
    source: str | None = None,
    subset: Literal["all", "non_overlapping", "high_confidence"] = "all",
    window: Literal["7d", "30d", "90d", "all"] = "30d",
    bins: Annotated[int, Query(ge=2, le=20)] = 10,
) -> CalibrationOut:
    days = WINDOW_DAYS[window]
    since = clock.now() - timedelta(days=days) if days else None
    rows = metrics.filter_subset(
        await repo.resolved_rows(symbol=symbol, horizon=horizon, source=source, since=since),
        subset,
    )
    module_rows = await repo.resolved_module_rows(symbol=symbol, horizon=horizon, since=since)
    if subset == "non_overlapping":
        module_rows = [row for row in module_rows if row.non_overlapping]
    reference = _reference_hit_rate(
        await repo.resolved_rows(symbol=symbol, horizon=horizon, source="baseline", since=since)
    )
    pending = len(
        await repo.list_predictions(
            symbol=symbol, horizon=horizon, source=source, resolved=False, limit=500
        )
    )
    return CalibrationOut(
        subset=subset,
        window_days=days,
        overall=SummaryOut(**_summary_fields(metrics.summarize(rows))),
        by_model=_by_model(rows),
        by_horizon=_by_horizon(rows),
        by_module=_by_module(module_rows, reference),
        reference_hit_rate=reference,
        bins=[
            CalibrationBinOut(
                bin=b.bin,
                lower=b.lower,
                upper=b.upper,
                n=b.n,
                mean_p=b.mean_p,
                observed_freq=b.observed_freq,
            )
            for b in metrics.calibration_bins(rows, bin_count=bins)
        ],
        daily=[
            DailyPointOut(day=p.day, n=p.n, brier=p.brier, hit_rate=p.hit_rate)
            for p in metrics.daily_series(rows)
        ],
        pending=pending,
    )
