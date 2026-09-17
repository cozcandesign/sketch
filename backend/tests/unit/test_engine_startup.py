"""Engine açılışı ve sağlık kaydı (F3-10).

Canlı çalıştırmada görülen iki yanlış: `spot_klines` çalışırken şeritte "aksıyor" görünüyordu,
funding geçmişi ilk 8 saat boyunca boş kalıyordu. İkisi de burada kilitlenir.
"""

from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.engine.health import HealthRegistry
from marketpulse.engine.main import _startup_backfills

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


class _FakeCollector:
    """Geçmiş tamamlayan bir toplayıcının açılışta gereken yüzeyi."""

    def __init__(self, name: str, *, fails: bool = False) -> None:
        self.name = name
        self.calls = 0
        self._fails = fails

    async def backfill(self) -> int:
        self.calls += 1
        if self._fails:
            raise RuntimeError("binance yanıt vermedi")
        return 7


class _FakeDerivatives:
    def __init__(self, funding: _FakeCollector, open_interest: _FakeCollector) -> None:
        self.funding = funding
        self.open_interest = open_interest


async def test_startup_fills_the_derivative_history_once() -> None:
    """funding_hist 8 saatte bir koşar; açılışta koşmazsa funding_dev bileşeni hesaba giremez."""
    health = HealthRegistry(FakeClock(T0))
    funding, open_interest = _FakeCollector("funding"), _FakeCollector("open_interest")

    await _startup_backfills(_FakeDerivatives(funding, open_interest), health)  # type: ignore[arg-type]

    assert (funding.calls, open_interest.calls) == (1, 1)
    assert health.status_of("funding") == "ok"
    assert health.status_of("open_interest") == "ok"


async def test_a_failing_backfill_does_not_block_the_other() -> None:
    """Collector'lar istisna yükseltmez (CLAUDE.md §6): biri patlarsa diğeri yine çalışır."""
    health = HealthRegistry(FakeClock(T0))
    funding = _FakeCollector("funding", fails=True)
    open_interest = _FakeCollector("open_interest")

    await _startup_backfills(_FakeDerivatives(funding, open_interest), health)  # type: ignore[arg-type]

    assert open_interest.calls == 1
    entry = next(row for row in health.snapshot() if row.collector == "funding")
    assert entry.consecutive_failures == 1
    assert entry.last_success_at is None


@pytest.mark.parametrize(("age_min", "expected"), [(4, "ok"), (15, "degraded"), (70, "down")])
def test_spot_klines_status_follows_the_gap_check_rhythm(age_min: int, expected: str) -> None:
    """`spot_klines` 5 dakikada bir `gap_check` ile beslenir, dolayısıyla taze kalır.

    Eşikler kısa periyotlu işler için 10 dk / 1 saat tabanına oturur (periyodun 1.5 ve 3 katı
    bunun altında kalır): tek bir gecikmiş tur yanlış alarm üretmesin.
    """
    clock = FakeClock(T0)
    health = HealthRegistry(clock)
    health.register("spot_klines", expected_interval=timedelta(minutes=5))
    health.record_success("spot_klines")

    clock.set(T0 + timedelta(minutes=age_min))

    assert health.status_of("spot_klines") == expected
