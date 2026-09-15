from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock
from marketpulse.engine.ratelimit import RateLimiter, WeightLimit

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _limiter(clock: FakeClock, **kwargs: object) -> tuple[RateLimiter, list[float]]:
    """Uyuduğunda sahte saati ilerleten limiter (aksi halde test sonsuz döner)."""
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock.advance(timedelta(seconds=seconds))

    return RateLimiter(clock, sleep=sleep, **kwargs), slept  # type: ignore[arg-type]


async def test_acquire_under_limit_does_not_sleep() -> None:
    clock = FakeClock(T0)
    limiter, slept = _limiter(clock, limit=100)
    await limiter.acquire(10)
    await limiter.acquire(10)
    assert limiter.used == 20
    assert slept == []


async def test_soft_threshold_spreads_requests() -> None:
    clock = FakeClock(T0)
    limiter, slept = _limiter(clock, limit=100, soft_ratio=0.5)
    await limiter.acquire(40)
    assert slept == []
    await limiter.acquire(20)  # 60 > %50 → seyreltme
    assert len(slept) == 1


async def test_waits_for_next_window_when_full() -> None:
    clock = FakeClock(T0)
    limiter, slept = _limiter(clock, limit=100)
    await limiter.acquire(100)
    await limiter.acquire(10)
    assert slept  # pencere sonuna kadar beklendi
    assert clock.now() >= T0 + timedelta(minutes=1)
    assert limiter.used == 10  # yeni pencerede sayaç sıfırlandı


async def test_used_weight_header_overrides_local_counter() -> None:
    clock = FakeClock(T0)
    limiter, _ = _limiter(clock, limit=100)
    await limiter.acquire(5)
    limiter.observe_used_weight(90)
    assert limiter.used == 90
    limiter.observe_used_weight(10)  # geriye gitmez
    assert limiter.used == 90


async def test_block_for_pauses_until_deadline() -> None:
    clock = FakeClock(T0)
    limiter, slept = _limiter(clock, limit=100)
    limiter.block_for(30)
    assert limiter.blocked_until == T0 + timedelta(seconds=30)
    await limiter.acquire(1)
    assert sum(slept) >= 30
    assert limiter.blocked_until is None


def test_apply_limit_from_exchange_info() -> None:
    clock = FakeClock(T0)
    limiter, _ = _limiter(clock, limit=100)
    limiter.apply_limit(WeightLimit(limit=6000, window=timedelta(minutes=1)))
    assert limiter.limit == 6000


@pytest.mark.parametrize("weight", [1, 50])
async def test_window_rolls_with_wall_clock(weight: int) -> None:
    clock = FakeClock(T0)
    limiter, _ = _limiter(clock, limit=100)
    await limiter.acquire(weight)
    clock.advance(timedelta(minutes=1))
    assert limiter.used == 0
