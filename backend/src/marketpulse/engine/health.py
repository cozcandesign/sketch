"""Collector sağlık kaydı.

Bellekte tutulur, heartbeat işinde DB'ye yazılır, durum geçişlerinde `health.changed` yayınlar.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from loguru import logger

from marketpulse.core.clock import Clock
from marketpulse.storage.models import CollectorHealth, HealthStatus
from marketpulse.storage.outbox import Outbox
from marketpulse.storage.repository import Repository

DEGRADED_AFTER = timedelta(minutes=10)
DOWN_AFTER = timedelta(hours=1)
DOWN_AFTER_FAILURES_WITHOUT_SUCCESS = 3
# Periyodu bilinen işler için eşikler kendi periyoduna göre ölçeklenir: 4 saatte bir çalışan bir iş
# sabit 1 saatlik eşikle saatlerce "kopuk" görünürdü. Yanlış alarm, şeridin güvenilirliğini bitirir.
DEGRADED_AFTER_PERIODS = 1.5
DOWN_AFTER_PERIODS = 3.0


@dataclass
class _Entry:
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    forced_status: HealthStatus | None = None
    known_failures: list[str] = field(default_factory=list)
    expected_interval: timedelta | None = None  # None = sürekli çalışan collector


class HealthRegistry:
    """Collector ve görev sağlığı. Durum türetme kuralı ARCHITECTURE.md §4."""

    def __init__(
        self,
        clock: Clock,
        *,
        degraded_after: timedelta = DEGRADED_AFTER,
        down_after: timedelta = DOWN_AFTER,
    ) -> None:
        self._clock = clock
        self._degraded_after = degraded_after
        self._down_after = down_after
        self._entries: dict[str, _Entry] = {}
        self._last_flushed: dict[str, HealthStatus] = {}

    def register(
        self,
        name: str,
        *,
        status: HealthStatus | None = None,
        expected_interval: timedelta | None = None,
    ) -> None:
        """Kaydı açar. `expected_interval` verilirse eşikler o periyoda göre ölçeklenir."""
        entry = self._entries.setdefault(name, _Entry())
        if status is not None:
            entry.forced_status = status
        if expected_interval is not None:
            entry.expected_interval = expected_interval

    def record_success(self, name: str) -> None:
        entry = self._entries.setdefault(name, _Entry())
        entry.last_success_at = self._clock.now()
        entry.consecutive_failures = 0

    def record_error(self, name: str, exc: BaseException | str) -> None:
        entry = self._entries.setdefault(name, _Entry())
        entry.last_error_at = self._clock.now()
        entry.last_error = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        entry.consecutive_failures += 1

    def set_status(self, name: str, status: HealthStatus | None) -> None:
        """`disabled` / `budget_exhausted` gibi zorlanmış durum; None ile türetmeye dönülür."""
        self._entries.setdefault(name, _Entry()).forced_status = status

    def status_of(self, name: str) -> HealthStatus:
        entry = self._entries[name]
        if entry.forced_status is not None:
            return entry.forced_status
        now = self._clock.now()
        if entry.last_success_at is None:
            if entry.consecutive_failures >= DOWN_AFTER_FAILURES_WITHOUT_SUCCESS:
                return "down"
            return "degraded" if entry.consecutive_failures > 0 else "ok"
        age = now - entry.last_success_at
        degraded_after, down_after = self._thresholds(entry)
        if age < degraded_after:
            return "ok"
        if age < down_after:
            return "degraded"
        return "down"

    def _thresholds(self, entry: _Entry) -> tuple[timedelta, timedelta]:
        """Periyodu bilinen iş kendi ritmine göre ölçülür; bilinmeyen sabit eşiklerle."""
        if entry.expected_interval is None:
            return self._degraded_after, self._down_after
        return (
            max(self._degraded_after, entry.expected_interval * DEGRADED_AFTER_PERIODS),
            max(self._down_after, entry.expected_interval * DOWN_AFTER_PERIODS),
        )

    def snapshot(self) -> list[CollectorHealth]:
        return [
            CollectorHealth(
                collector=name,
                status=self.status_of(name),
                last_success_at=e.last_success_at,
                last_error_at=e.last_error_at,
                last_error=e.last_error,
                consecutive_failures=e.consecutive_failures,
            )
            for name, e in sorted(self._entries.items())
        ]

    async def flush(self, repo: Repository, outbox: Outbox | None = None) -> list[CollectorHealth]:
        """Tüm kayıtları DB'ye yazar; durum değişenler için `health.changed` yayınlar."""
        rows = self.snapshot()
        await repo.upsert_collector_health_many(rows)
        for row in rows:
            previous = self._last_flushed.get(row.collector)
            if previous != row.status:
                self._last_flushed[row.collector] = row.status
                logger.bind(collector=row.collector).info(
                    "sağlık durumu {prev} → {new}", prev=previous, new=row.status
                )
                if outbox is not None:
                    await outbox.emit(
                        "health.changed",
                        {
                            "collector": row.collector,
                            "status": row.status,
                            "last_success_at": row.last_success_at,
                            "last_error": row.last_error,
                        },
                    )
        return rows
