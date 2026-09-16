from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.types import Horizon
from marketpulse.storage.models import ModuleResolvedRow, ResolvedRow
from marketpulse.tracking import metrics

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def row(
    p_up: float,
    y: int,
    *,
    day: int = 0,
    non_overlapping: bool = True,
    confidence_label: str = "low",
) -> ResolvedRow:
    return ResolvedRow(
        symbol="BTCUSDT",
        horizon=Horizon.H1H,
        as_of=T0 + timedelta(days=day),
        source="baseline",
        ensemble_version="baseline-climatology-1",
        p_up=p_up,
        y=y,
        brier=(p_up - y) ** 2,
        hit=(p_up > 0.5) == bool(y),
        non_overlapping=non_overlapping,
        confidence_label=confidence_label,  # type: ignore[arg-type]
    )


def test_brier_score_hand_computed() -> None:
    # (0.8-1)² = 0.04, (0.6-0)² = 0.36, (0.5-1)² = 0.25 → ortalama 0.21666...
    rows = [row(0.8, 1), row(0.6, 0), row(0.5, 1)]
    assert metrics.brier_score(rows) == pytest.approx((0.04 + 0.36 + 0.25) / 3)


def test_perfect_and_worst_case_brier() -> None:
    assert metrics.brier_score([row(1.0, 1), row(0.0, 0)]) == 0.0
    assert metrics.brier_score([row(1.0, 0), row(0.0, 1)]) == 1.0
    assert metrics.brier_score([row(0.5, 1), row(0.5, 0)]) == 0.25  # bilgisiz


def test_brier_skill_score_positive_when_better_than_base_rate() -> None:
    # Brier = (0.01+0.01+0.04+0.04)/4 = 0.025; taban oranı 0.5 → referans Brier 0.25
    # BSS = 1 - 0.025/0.25 = 0.9
    rows = [row(0.9, 1), row(0.1, 0), row(0.8, 1), row(0.2, 0)]
    assert metrics.brier_score(rows) == pytest.approx(0.025)
    assert metrics.brier_skill_score(rows) == pytest.approx(0.9)


def test_brier_skill_score_negative_when_worse_than_base_rate() -> None:
    rows = [row(0.1, 1), row(0.9, 0), row(0.2, 1), row(0.8, 0)]
    bss = metrics.brier_skill_score(rows)
    assert bss is not None
    assert bss < 0


def test_brier_skill_is_none_when_all_outcomes_identical() -> None:
    assert metrics.brier_skill_score([row(0.7, 1), row(0.6, 1)]) is None


def test_base_rate_and_hit_rate() -> None:
    rows = [row(0.7, 1), row(0.7, 1), row(0.7, 0), row(0.3, 0)]
    assert metrics.base_rate(rows) == 0.5
    assert metrics.hit_rate(rows) == 0.75  # 3/4


def test_wilson_interval_known_values() -> None:
    # 50/100 → yaklaşık 0.404 .. 0.596 (standart Wilson %95)
    interval = metrics.wilson_interval(50, 100)
    assert interval.low == pytest.approx(0.4038, abs=1e-3)
    assert interval.high == pytest.approx(0.5962, abs=1e-3)
    # Küçük örneklem geniş aralık verir: 5 denemede 3 isabet
    small = metrics.wilson_interval(3, 5)
    assert small.low < 0.3
    assert small.high > 0.85
    empty = metrics.wilson_interval(0, 0)
    assert (empty.low, empty.high) == (0.0, 1.0)


def test_calibration_bins_group_by_probability() -> None:
    rows = [row(0.05, 0), row(0.05, 0), row(0.95, 1), row(0.95, 1), row(0.55, 1)]
    bins = metrics.calibration_bins(rows, bin_count=10)
    assert len(bins) == 10
    assert bins[0].n == 2
    assert bins[0].observed_freq == 0.0
    assert bins[9].n == 2
    assert bins[9].observed_freq == 1.0
    assert bins[5].n == 1
    assert bins[5].mean_p == pytest.approx(0.55)
    assert bins[1].n == 0
    assert bins[1].mean_p is None


def test_calibration_bin_edges_are_inclusive_at_one() -> None:
    bins = metrics.calibration_bins([row(1.0, 1)], bin_count=10)
    assert bins[9].n == 1


def test_daily_series_groups_by_utc_day() -> None:
    rows = [row(0.8, 1, day=0), row(0.6, 0, day=0), row(0.9, 1, day=1)]
    series = metrics.daily_series(rows)
    assert [p.day.isoformat() for p in series] == ["2026-01-01", "2026-01-02"]
    assert series[0].n == 2
    assert series[1].brier == pytest.approx(0.01)


def test_summarize_empty_is_safe() -> None:
    summary = metrics.summarize([])
    assert summary.n == 0
    assert summary.brier is None
    assert summary.beats_uninformed is False


def test_summarize_reports_ci_and_uninformed_comparison() -> None:
    rows = [row(0.8, 1) for _ in range(40)] + [row(0.2, 0) for _ in range(40)]
    summary = metrics.summarize(rows)
    assert summary.n == 80
    assert summary.hit_rate == 1.0
    assert summary.hit_ci is not None
    assert summary.hit_ci.low > 0.9
    assert summary.beats_uninformed


def test_filter_subset() -> None:
    rows = [
        row(0.7, 1, non_overlapping=True, confidence_label="high"),
        row(0.7, 1, non_overlapping=False, confidence_label="low"),
    ]
    assert len(metrics.filter_subset(rows, "all")) == 2
    assert len(metrics.filter_subset(rows, "non_overlapping")) == 1
    assert len(metrics.filter_subset(rows, "high_confidence")) == 1


# --- modül isabeti (K26) ---


def module_row(
    module: str, score: float, y: int, *, coverage: float = 1.0, non_overlapping: bool = True
) -> ModuleResolvedRow:
    return ModuleResolvedRow(
        module=module,
        score=score,
        coverage=coverage,
        horizon=Horizon.H1H,
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        non_overlapping=non_overlapping,
        y=y,
    )


def test_module_hit_rate_uses_the_sign_of_the_score() -> None:
    rows = [
        module_row("technical", 0.5, 1),  # yukarı dedi, yukarı oldu
        module_row("technical", 0.4, 0),  # yukarı dedi, aşağı oldu
        module_row("technical", -0.6, 0),  # aşağı dedi, aşağı oldu
        module_row("technical", -0.3, 0),  # aşağı dedi, aşağı oldu
    ]
    summary = metrics.module_summary(rows, "technical")
    assert summary.n == 4
    assert summary.hit_rate == pytest.approx(0.75)
    assert summary.hit_ci is not None
    assert summary.hit_ci.low < 0.75 < summary.hit_ci.high


def test_weak_scores_do_not_count_as_a_direction_call() -> None:
    """|skor| < 0.1 "yön söylemiyor": isabet ölçümüne girmez, atlandı olarak sayılır."""
    rows = [module_row("technical", 0.02, 0), module_row("technical", 0.5, 1)]
    summary = metrics.module_summary(rows, "technical")
    assert summary.n == 1
    assert summary.skipped == 1
    assert summary.hit_rate == pytest.approx(1.0)


def test_rows_without_coverage_are_not_measured() -> None:
    rows = [module_row("orderflow", 0.0, 1, coverage=0.0)]
    summary = metrics.module_summary(rows, "orderflow")
    assert summary.n == 0
    assert summary.hit_rate is None
    assert summary.beats(0.5) is None


def test_a_module_beats_the_reference_only_when_its_lower_bound_is_above_it() -> None:
    """K26: üstünlük noktasal isabetle değil, güven aralığının ALT sınırıyla kanıtlanır."""
    strong = [module_row("technical", 0.5, 1) for _ in range(200)]
    summary = metrics.module_summary(strong, "technical")
    assert summary.beats(0.52) is True

    coin_flip = [module_row("technical", 0.5, index % 2) for index in range(200)]
    weak = metrics.module_summary(coin_flip, "technical")
    assert weak.hit_rate == pytest.approx(0.5)
    assert weak.beats(0.52) is False


def test_the_proof_sample_threshold_is_two_hundred() -> None:
    few = metrics.module_summary([module_row("technical", 0.5, 1) for _ in range(199)], "technical")
    enough = metrics.module_summary(
        [module_row("technical", 0.5, 1) for _ in range(200)], "technical"
    )
    assert not few.has_proof_sample
    assert enough.has_proof_sample


def test_the_reference_line_is_the_best_of_the_baselines() -> None:
    better = metrics.MetricsSummary(10, 0.2, 0.1, 0.5, 0.62, None)
    worse = metrics.MetricsSummary(10, 0.3, 0.0, 0.5, 0.48, None)
    assert metrics.best_reference_hit_rate([better, worse]) == pytest.approx(0.62)
    assert metrics.best_reference_hit_rate([]) is None


def test_module_summaries_cover_every_module_present() -> None:
    rows = [module_row("technical", 0.5, 1), module_row("macro", -0.4, 0)]
    assert [s.module for s in metrics.module_summaries(rows)] == ["macro", "technical"]
