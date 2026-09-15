from pathlib import Path

import pytest

from marketpulse.config import Settings, find_env_file, load_settings
from marketpulse.core.errors import ConfigError


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert s.llm_tier1_model == "claude-haiku-4-5"
    assert s.llm_tier2_model == "claude-sonnet-5"
    assert s.llm_daily_budget_usd == 3.0
    assert s.anthropic_api_key is None
    assert s.sqlite_path == Path("./data/marketpulse.db")
    assert s.sync_db_url.startswith("sqlite:///")


def test_csv_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MP_SYMBOLS", "btcusdt, ethusdt")
    monkeypatch.setenv("MP_CORS_ORIGINS", "http://a:1,http://b:2")
    s = Settings(_env_file=None)
    assert s.symbols == ["BTCUSDT", "ETHUSDT"]
    assert s.cors_origins == ["http://a:1", "http://b:2"]


def test_secret_keys_without_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    s = Settings(_env_file=None)
    assert s.anthropic_api_key is not None
    assert s.anthropic_api_key.get_secret_value() == "sk-test"
    assert "sk-test" not in repr(s)


def test_invalid_symbol_in_env_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MP_SYMBOLS", "BTC-USDT")
    with pytest.raises(ValueError, match="geçersiz sembol"):
        Settings(_env_file=None)


def test_budget_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MP_LLM_DAILY_BUDGET_USD", "0")
    with pytest.raises(ValueError, match="pozitif"):
        Settings(_env_file=None)


def test_load_settings_without_env_file_or_mp_env_gives_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MP_ENV", raising=False)
    with pytest.raises(ConfigError, match=r"cp \.env\.example \.env"):
        load_settings()


def test_load_settings_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MP_ENV", raising=False)
    (tmp_path / ".env").write_text("MP_ENV=prod\nMP_SYMBOLS=BTCUSDT\nMP_API_PORT=8123\n")
    sub = tmp_path / "backend"
    sub.mkdir()
    monkeypatch.chdir(sub)  # bir alt dizinden de bulunmalı
    assert find_env_file() == tmp_path / ".env"
    s = load_settings()
    assert s.env == "prod"
    assert s.symbols == ["BTCUSDT"]
    assert s.api_port == 8123


def test_load_settings_with_mp_env_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MP_ENV", "dev")
    assert load_settings().env == "dev"
