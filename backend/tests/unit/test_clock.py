from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.core.clock import FakeClock, SystemClock


def test_system_clock_is_utc() -> None:
    assert SystemClock().now().utcoffset() == timedelta(0)


def test_fake_clock_advance_and_set() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    assert clock.advance(timedelta(minutes=5)) == datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    clock.set(datetime(2027, 1, 1, tzinfo=UTC))
    assert clock.now().year == 2027


def test_fake_clock_rejects_naive() -> None:
    with pytest.raises(ValueError, match="naive"):
        FakeClock(datetime(2026, 1, 1))  # noqa: DTZ001 - kasıtlı naive
