"""Doğruluk metrikleri (ARCHITECTURE.md §11.2).

Tanımlar:
- **Brier skoru**: `ortalama((p_up − y)²)`. 0 mükemmel, 0.25 bilgisiz (hep %50 demek), küçük iyi.
- **Brier skill score (BSS)**: `1 − Brier / Brier_ref`; `Brier_ref` sabit taban oranı tahminidir.
  Pozitifse tahmin bilgisizden iyidir.
- **Kalibrasyon eğrisi**: olasılık kovalarında "söylenen olasılık" ile "gerçekleşen oran" farkı.
- **İsabet oranı**: yön doğru bilinen tahmin oranı, Wilson %95 güven aralığıyla.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from marketpulse.storage.models import ModuleResolvedRow, ResolvedRow

Z_95 = 1.959963984540054
DEFAULT_BINS = 10
UNINFORMED_BRIER = 0.25


@dataclass(frozen=True)
class Interval95:
    low: float
    high: float


@dataclass(frozen=True)
class CalibrationBin:
    bin: int
    lower: float
    upper: float
    n: int
    mean_p: float | None
    observed_freq: float | None


@dataclass(frozen=True)
class DailyPoint:
    day: date
    n: int
    brier: float
    hit_rate: float


@dataclass(frozen=True)
class MetricsSummary:
    n: int
    brier: float | None
    brier_skill: float | None
    base_rate: float | None
    hit_rate: float | None
    hit_ci: Interval95 | None

    @property
    def beats_uninformed(self) -> bool:
        return self.brier is not None and self.brier < UNINFORMED_BRIER


def wilson_interval(successes: int, n: int, z: float = Z_95) -> Interval95:
    """Oran için Wilson %95 güven aralığı. Küçük örneklemde normal yaklaşımdan daha güvenilir."""
    if n <= 0:
        return Interval95(0.0, 1.0)
    p = successes / n
    denominator = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denominator
    half = (z / denominator) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return Interval95(low=max(0.0, center - half), high=min(1.0, center + half))


def brier_score(rows: Sequence[ResolvedRow]) -> float | None:
    if not rows:
        return None
    return sum((r.p_up - r.y) ** 2 for r in rows) / len(rows)


def base_rate(rows: Sequence[ResolvedRow]) -> float | None:
    """Gerçekleşen "yukarı" oranı. Referans Brier bu sabit tahminle hesaplanır."""
    if not rows:
        return None
    return sum(r.y for r in rows) / len(rows)


def brier_skill_score(rows: Sequence[ResolvedRow]) -> float | None:
    rate = base_rate(rows)
    score = brier_score(rows)
    if rate is None or score is None:
        return None
    reference = sum((rate - r.y) ** 2 for r in rows) / len(rows)
    if reference == 0:
        return None  # tüm sonuçlar aynı yönde: karşılaştırma anlamsız
    return 1 - score / reference


def hit_rate(rows: Sequence[ResolvedRow]) -> float | None:
    if not rows:
        return None
    return sum(1 for r in rows if r.hit) / len(rows)


def calibration_bins(
    rows: Sequence[ResolvedRow], *, bin_count: int = DEFAULT_BINS
) -> list[CalibrationBin]:
    """Olasılığı `bin_count` kovaya böler; her kovada ortalama olasılık ve gözlenen oran."""
    buckets: list[list[ResolvedRow]] = [[] for _ in range(bin_count)]
    for row in rows:
        index = min(bin_count - 1, max(0, int(row.p_up * bin_count)))
        buckets[index].append(row)
    result: list[CalibrationBin] = []
    for index, bucket in enumerate(buckets):
        result.append(
            CalibrationBin(
                bin=index,
                lower=index / bin_count,
                upper=(index + 1) / bin_count,
                n=len(bucket),
                mean_p=(sum(r.p_up for r in bucket) / len(bucket)) if bucket else None,
                observed_freq=(sum(r.y for r in bucket) / len(bucket)) if bucket else None,
            )
        )
    return result


def daily_series(rows: Sequence[ResolvedRow]) -> list[DailyPoint]:
    """Gün bazında (UTC, `as_of`) Brier ve isabet serisi."""
    grouped: dict[date, list[ResolvedRow]] = {}
    for row in rows:
        grouped.setdefault(row.as_of.date(), []).append(row)
    points: list[DailyPoint] = []
    for day in sorted(grouped):
        bucket = grouped[day]
        score = brier_score(bucket)
        rate = hit_rate(bucket)
        if score is None or rate is None:
            continue
        points.append(DailyPoint(day=day, n=len(bucket), brier=score, hit_rate=rate))
    return points


def summarize(rows: Sequence[ResolvedRow]) -> MetricsSummary:
    if not rows:
        return MetricsSummary(0, None, None, None, None, None)
    hits = sum(1 for r in rows if r.hit)
    return MetricsSummary(
        n=len(rows),
        brier=brier_score(rows),
        brier_skill=brier_skill_score(rows),
        base_rate=base_rate(rows),
        hit_rate=hits / len(rows),
        hit_ci=wilson_interval(hits, len(rows)),
    )


def filter_subset(rows: Sequence[ResolvedRow], subset: str) -> list[ResolvedRow]:
    """`all` | `non_overlapping` | `high_confidence` alt kümesi."""
    if subset == "non_overlapping":
        return [r for r in rows if r.non_overlapping]
    if subset == "high_confidence":
        return [r for r in rows if r.confidence_label == "high"]
    return list(rows)


# --- modül isabeti (ARCHITECTURE.md §11.2, K26) ---

MODULE_MIN_SCORE: Final = 0.1  # bu şiddetin altındaki skor "yön söylemiyor": sayılmaz
PROOF_SAMPLE: Final = 200  # K26: ispat için gereken asgari çözümlenmiş tahmin


@dataclass(frozen=True)
class ModuleSummary:
    """Tek modülün yön isabeti. `skipped`: skoru çok zayıf olduğu için sayılmayan tahminler."""

    module: str
    n: int
    skipped: int
    hit_rate: float | None
    hit_ci: Interval95 | None

    def beats(self, reference: float | None) -> bool | None:
        """Wilson alt sınırı referans isabetini geçiyor mu? Veri yoksa `None` ("bilinmiyor")."""
        if self.hit_ci is None or reference is None:
            return None
        return self.hit_ci.low > reference

    @property
    def has_proof_sample(self) -> bool:
        """K26: en az 200 çözümlenmiş tahmin birikmeden hüküm verilmez."""
        return self.n >= PROOF_SAMPLE


def module_summary(
    rows: Sequence[ModuleResolvedRow], module: str, *, min_score: float = MODULE_MIN_SCORE
) -> ModuleSummary:
    """Modül skorunun işareti yönü verir; zayıf skorlar ölçüme girmez."""
    own = [row for row in rows if row.module == module and row.coverage > 0]
    voting = [row for row in own if abs(row.score) >= min_score]
    if not voting:
        return ModuleSummary(module=module, n=0, skipped=len(own), hit_rate=None, hit_ci=None)
    hits = sum(1 for row in voting if (row.score > 0) == (row.y == 1))
    return ModuleSummary(
        module=module,
        n=len(voting),
        skipped=len(own) - len(voting),
        hit_rate=hits / len(voting),
        hit_ci=wilson_interval(hits, len(voting)),
    )


def module_summaries(rows: Sequence[ModuleResolvedRow]) -> list[ModuleSummary]:
    return [module_summary(rows, module) for module in sorted({row.module for row in rows})]


def best_reference_hit_rate(summaries: Sequence[MetricsSummary]) -> float | None:
    """Referans tahmincilerin en iyisinin isabet oranı: modülün aşması gereken çizgi (K26)."""
    rates = [summary.hit_rate for summary in summaries if summary.hit_rate is not None]
    return max(rates) if rates else None
