"""Ortak pytest fixture'ları."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from marketpulse.core.clock import FakeClock

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
