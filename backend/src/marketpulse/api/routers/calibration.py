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
    SummaryOut,
)
from marketpulse.core.clock import Clock
from marketpulse.core.types import Horizon
from marketpulse.storage.models import ResolvedRow
from marketpulse.storage.repository import Repository
from marketpulse.tracking import metrics

router = APIRouter(tags=["calibration"])

WINDOW_DAYS: dict[str, int | None] = {"7d": 7, "30d": 30, "90d": 90, "all": None}
MODEL_LABELS_TR: dict[str, str] = {
    "baseline-climatology-1": "Referans: taban oranı",
    "baseline-momentum-1": "Referans: son mum rengi",
}


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
