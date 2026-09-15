from datetime import UTC, datetime, timedelta, timezone

import pytest

from marketpulse.core.time import (
    ensure_utc,
    floor_to,
    floor_to_minute,
    from_epoch_ms,
    is_aligned,
    to_epoch_ms,
    utc_now,
)


def test_utc_now_is_aware_utc() -> None:
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_ensure_utc_rejects_naive() -> None:
    with pytest.raises(ValueError, match="naive"):
        ensure_utc(datetime(2026, 1, 1, 12, 0))  # noqa: DTZ001 - kasıtlı naive


def test_ensure_utc_converts_offset() -> None:
    ist = timezone(timedelta(hours=3))
    dt = datetime(2026, 1, 1, 15, 0, tzinfo=ist)
    assert ensure_utc(dt) == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("minute", "second", "expected_minute"),
    [(0, 0, 0), (7, 59, 0), (15, 0, 15), (29, 59, 15), (44, 1, 30), (59, 59, 45)],
)
def test_floor_to_15_minutes(minute: int, second: int, expected_minute: int) -> None:
    dt = datetime(2026, 3, 4, 10, minute, second, 123456, tzinfo=UTC)
    got = floor_to(dt, timedelta(minutes=15))
    assert got == datetime(2026, 3, 4, 10, expected_minute, tzinfo=UTC)


def test_floor_to_minute_drops_seconds() -> None:
    dt = datetime(2026, 3, 4, 10, 5, 59, 999999, tzinfo=UTC)
    assert floor_to_minute(dt) == datetime(2026, 3, 4, 10, 5, tzinfo=UTC)


def test_floor_to_rejects_nonpositive_step() -> None:
    with pytest.raises(ValueError, match="pozitif"):
        floor_to(utc_now(), timedelta(0))


def test_is_aligned_24h_only_at_midnight_utc() -> None:
    day = timedelta(hours=24)
    assert is_aligned(datetime(2026, 3, 4, 0, 0, tzinfo=UTC), day)
    assert not is_aligned(datetime(2026, 3, 4, 4, 0, tzinfo=UTC), day)


def test_epoch_ms_roundtrip() -> None:
    dt = datetime(2026, 3, 4, 10, 5, 7, 250000, tzinfo=UTC)
    assert from_epoch_ms(to_epoch_ms(dt)) == dt
